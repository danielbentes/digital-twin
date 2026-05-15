#!/usr/bin/env python3
"""
extract-twin-spec.py — Behavioral Twin v1 extraction pass.

Reads Phase 5 deep-read reports, Phase 5.5 insights, quantitative stats, and
Phase 4 deep-source inventories, then asks Claude to produce a compact
substitution spec used by synthesize.py to render ~/.claude/agents/twin.md and
generated CLAUDE rules.

Outputs:
  ~/.claude/digital-twin/analysis/twin-spec.json

Exit codes:
  0 — success, or no reports/insights were available and --allow-empty was set
  2 — extraction failed or returned invalid JSON
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from glob import glob
from pathlib import Path

from twin_spec_validation import validate_twin_spec

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
SCHEMA_PATH = PLUGIN_ROOT / "references" / "twin-spec-schema.json"
PROMPT_PATH = PLUGIN_ROOT / "references" / "prompts" / "twin-spec-extraction.md"

JSON_OBJECT_RE = re.compile(r"\{[\s\S]*\}")


def load_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"WARN: could not read {path}: {exc}", file=sys.stderr)
        return ""


def load_json(path: Path, default=None):
    if not path.exists():
        return default
    try:
        with open(path, encoding="utf-8") as fp:
            return json.load(fp)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"WARN: could not load JSON {path}: {exc}", file=sys.stderr)
        return default


def build_stats_packet(analysis_dir: Path) -> str:
    packet = {}
    for key, fname in (
        ("numbers", "numbers.json"),
        ("temporal", "temporal.json"),
        ("convergence_pairs", "convergence-pairs.json"),
        ("plan_inventory", "plan-inventory.json"),
    ):
        data = load_json(analysis_dir / fname)
        if data is None:
            continue
        if not isinstance(data, dict):
            print(
                f"WARN: {analysis_dir / fname} did not contain a JSON object; skipping",
                file=sys.stderr,
            )
            continue
        if key == "numbers":
            data.pop("vocab", None)
            data.pop("top_unigrams", None)
            data.pop("top_bigrams", None)
        packet[key] = data

    mem_raw = load_json(analysis_dir / "memory-inventory.json", default={}) or {}
    mem = mem_raw if isinstance(mem_raw, dict) else {}
    packet["memory_inventory_summary"] = {
        "n_files": mem.get("n_files"),
        "by_type": mem.get("by_type"),
        "feedback_rules": [
            {
                "project": e.get("project"),
                "name": e.get("name"),
                "description": e.get("description"),
                "path": e.get("path"),
            }
            for e in mem.get("entries", [])
            if e.get("type") == "feedback"
        ][:60],
    }
    return json.dumps(packet, indent=2, ensure_ascii=False)


def build_reports_packet(reports_dir: Path) -> tuple[str, list[str]]:
    files = sorted(glob(str(reports_dir / "*.md")))
    blocks = []
    for fp in files:
        path = Path(fp)
        blocks.append(f"\n\n========== FILE: {path.name} ==========\n\n")
        blocks.append(load_text(path))
    return "".join(blocks), [Path(f).name for f in files]


def build_insights_packet(analysis_dir: Path) -> str:
    insights_dir = analysis_dir / "insights"
    if not insights_dir.exists():
        return "{}"
    packet = {}
    for fp in sorted(insights_dir.glob("*.json")):
        packet[fp.stem] = load_json(fp, default={})
    return json.dumps(packet, indent=2, ensure_ascii=False)


def fill_prompt(user_name: str, stats: str, insights: str, reports: str, schema: str) -> str:
    tpl = load_text(PROMPT_PATH)
    if not tpl:
        raise SystemExit(f"ERROR: prompt template not found at {PROMPT_PATH}")
    return (
        tpl.replace("{{USER_NAME}}", user_name)
        .replace("{{STATS_PACKET}}", stats)
        .replace("{{INSIGHTS_PACKET}}", insights)
        .replace("{{REPORTS_PACKET}}", reports)
        .replace("{{SCHEMA_JSON}}", schema)
    )


def call_claude_cli(prompt: str, model: str, timeout: int) -> str:
    if shutil.which("claude") is None:
        raise RuntimeError("claude CLI not on PATH")
    proc = subprocess.run(
        [
            "claude",
            "-p",
            "--model",
            model,
            "--output-format",
            "text",
            "--no-session-persistence",
        ],
        input=prompt,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"claude CLI failed (rc={proc.returncode}): {proc.stderr.strip()[:500]}"
        )
    return proc.stdout


def strip_to_json(raw: str) -> str:
    s = raw.strip()
    if s.startswith("```"):
        s = re.sub(r"^```(?:json)?\s*\n", "", s)
        s = re.sub(r"\n```\s*$", "", s)
        s = s.strip()
    if not s.startswith("{"):
        m = JSON_OBJECT_RE.search(s)
        if m:
            s = m.group(0)
    return s


def validate_spec(obj: dict) -> list[str]:
    return validate_twin_spec(obj, SCHEMA_PATH)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--analysis-dir", default=os.path.expanduser("~/.claude/digital-twin/analysis"))
    ap.add_argument("--reports-dir", default=os.path.expanduser("~/.claude/digital-twin/analysis/reports"))
    ap.add_argument("--out-json", default=os.path.expanduser("~/.claude/digital-twin/analysis/twin-spec.json"))
    ap.add_argument("--user-name", default=os.environ.get("DIGITAL_TWIN_USER_NAME", os.environ.get("USER", "user")))
    ap.add_argument("--model", default="sonnet")
    ap.add_argument("--timeout", type=int, default=900)
    ap.add_argument("--mock-response-file", help="Use a local JSON response instead of calling Claude.")
    ap.add_argument("--allow-empty", action="store_true", help="Exit 0 if no reports/insights are available.")
    args = ap.parse_args()

    analysis_dir = Path(args.analysis_dir).expanduser()
    reports_dir = Path(args.reports_dir).expanduser()
    out_json = Path(args.out_json).expanduser()
    out_json.parent.mkdir(parents=True, exist_ok=True)

    reports_packet, report_files = build_reports_packet(reports_dir)
    insights_packet = build_insights_packet(analysis_dir)
    if not report_files and insights_packet == "{}":
        msg = "WARN: no reports or insights available for twin spec extraction"
        print(msg, file=sys.stderr)
        return 0 if args.allow_empty else 2

    if args.mock_response_file:
        mock_path = Path(args.mock_response_file).expanduser()
        if not mock_path.exists():
            print(
                f"ERROR: --mock-response-file path not found: {mock_path}",
                file=sys.stderr,
            )
            return 2
        try:
            raw = mock_path.read_text(encoding="utf-8")
        except OSError as exc:
            print(
                f"ERROR: --mock-response-file unreadable ({mock_path}): {exc}",
                file=sys.stderr,
            )
            return 2
    else:
        schema_json = load_text(SCHEMA_PATH)
        prompt = fill_prompt(
            args.user_name,
            build_stats_packet(analysis_dir),
            insights_packet,
            reports_packet,
            schema_json,
        )
        try:
            raw = call_claude_cli(prompt, args.model, args.timeout)
        except Exception as e:
            print(f"ERROR: twin spec extraction failed: {e}", file=sys.stderr)
            return 2

    json_text = strip_to_json(raw)
    try:
        spec = json.loads(json_text)
    except json.JSONDecodeError as e:
        debug = out_json.with_suffix(".raw.txt")
        debug.write_text(raw, encoding="utf-8")
        print(f"ERROR: twin spec response was not valid JSON: {e}", file=sys.stderr)
        print(f"Wrote raw response: {debug}", file=sys.stderr)
        return 2

    errors = validate_spec(spec)
    if errors:
        debug = out_json.with_suffix(".invalid.json")
        debug.write_text(json.dumps(spec, indent=2, ensure_ascii=False), encoding="utf-8")
        print("ERROR: twin spec failed validation:", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        print(f"Wrote invalid spec: {debug}", file=sys.stderr)
        return 2

    out_json.write_text(json.dumps(spec, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote: {out_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
