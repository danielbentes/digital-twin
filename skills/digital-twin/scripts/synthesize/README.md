# Maintain the synthesis package

The synthesis package contains the implementation behind digital-twin
synthesis. The `synthesize.py` script remains the stable executable entry
point. Keep its wrapper command unchanged:

```bash
python3 skills/digital-twin/scripts/synthesize.py [arguments]
```

## Run the package locally

This package is repository-local: it lives in this repository and is not
installed as a Python distribution. For library use, set `PYTHONPATH`, the
environment variable that adds import locations, before importing
`synthesize`:

```bash
PYTHONPATH=skills/digital-twin/scripts python3 - <<'PY'
import synthesize

print(synthesize.CURRENT_SCHEMA_VERSION)
PY
```

Use the executable entry point for command-line work. Use the package modules
when another Python program needs to call synthesis functionality.

## Understand the modules

Each implementation module has one focused responsibility:

- `shared.py` provides shared paths, loaders, rendering helpers, and
  sanitization helpers.
- `profile_construction.py` builds profile narratives and structured cards.
- `profile_formatting.py` formats profiles and supports legacy-profile data.
- `spec_core.py` migrates, provides compatibility behavior for, and normalizes
  twin specifications.
- `twin_rendering.py` renders twin specifications as Markdown.
- `output_writing.py` writes final artifacts and rule files.
- `cli.py` parses command-line arguments and coordinates validation,
  synthesis, and output writing.

## Preserve dependency direction

Keep dependencies one-way. Treat `shared.py` as the foundational helper
module. `profile_construction.py` and `profile_formatting.py` may use it;
`twin_rendering.py` may use it and `spec_core.py`; `output_writing.py` may use
`twin_rendering.py`; and `cli.py` coordinates the higher-level modules. Do not
make a lower-level module import its caller. Never add circular imports.

## Preserve compatibility

`__init__.py` preserves the historical helper surface for compatibility. It
re-exports helpers from the implementation modules so existing callers can
continue to work. New code should import each symbol from its owning module,
for example:

```python
from synthesize.spec_core import normalize_twin_spec_for_rendering
```

Do not add new implementation logic to `__init__.py`.

## Verify changes

Run these commands from the repository root:

```bash
ruff check .
mypy skills/digital-twin/scripts tests
python3 -m pytest -q
python3 skills/digital-twin/scripts/evaluate-twin.py tests/fixtures/eval/heldout_cases.json
```

Run the evaluation command after changes that affect synthesis,
rendering, validation, or output.

## Maintain the package

Keep every implementation module at or below 800 lines. Preserve the
`synthesize.py` wrapper command and the exported compatibility surface in
`__init__.py` when refactoring. Add new functionality to the owning module,
then update compatibility exports only when an existing public helper needs to
remain available.
