#!/usr/bin/env python3
"""
Shared validation for behavioral twin specs.

This implements the small JSON Schema subset used by
references/twin-spec-schema.json so the pipeline does not depend on external
Python packages.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_schema(schema_path: Path) -> dict[str, Any]:
    try:
        with open(schema_path, encoding="utf-8") as fp:
            schema = json.load(fp)
    except (OSError, json.JSONDecodeError) as e:
        return {"_schema_load_error": f"{schema_path}: {e}"}
    return schema


def _type_name(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return type(value).__name__


def _matches_type(value: Any, expected: str) -> bool:
    if expected == "object":
        return isinstance(value, dict)
    if expected == "array":
        return isinstance(value, list)
    if expected == "string":
        return isinstance(value, str)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected == "boolean":
        return isinstance(value, bool)
    return True


def validate_json_schema_subset(
    value: Any,
    schema: dict[str, Any],
    path: str = "$",
) -> list[str]:
    """Validate the subset of draft-07 features used by twin-spec-schema.json."""
    errors: list[str] = []
    if "_schema_load_error" in schema:
        return [f"could not load schema: {schema['_schema_load_error']}"]

    expected_type = schema.get("type")
    if expected_type and not _matches_type(value, expected_type):
        return [f"{path}: expected {expected_type}, got {_type_name(value)}"]

    if expected_type == "object":
        required = schema.get("required") or []
        for key in required:
            if key not in value:
                errors.append(f"{path}.{key}: missing required field")

        properties = schema.get("properties") or {}
        for key, child_schema in properties.items():
            if key in value:
                errors.extend(
                    validate_json_schema_subset(value[key], child_schema, f"{path}.{key}")
                )

        additional = schema.get("additionalProperties")
        if isinstance(additional, dict):
            for key, child_value in value.items():
                if key not in properties:
                    errors.extend(
                        validate_json_schema_subset(
                            child_value,
                            additional,
                            f"{path}.{key}",
                        )
                    )

    if expected_type == "array":
        min_items = schema.get("minItems")
        max_items = schema.get("maxItems")
        if isinstance(min_items, int) and len(value) < min_items:
            errors.append(f"{path}: expected at least {min_items} items, got {len(value)}")
        if isinstance(max_items, int) and len(value) > max_items:
            errors.append(f"{path}: expected at most {max_items} items, got {len(value)}")
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for i, item in enumerate(value):
                errors.extend(validate_json_schema_subset(item, item_schema, f"{path}[{i}]"))

    if expected_type == "integer" and "minimum" in schema:
        minimum = schema["minimum"]
        if isinstance(minimum, (int, float)) and value < minimum:
            errors.append(f"{path}: expected >= {minimum}, got {value}")

    return errors


def validate_twin_spec(spec: Any, schema_path: Path) -> list[str]:
    schema = load_schema(schema_path)
    return validate_json_schema_subset(spec, schema)
