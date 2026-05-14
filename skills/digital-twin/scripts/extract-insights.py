#!/usr/bin/env python3
"""
extract-insights.py — Phase 5.5 of the digital-twin skill.

Reads the 6 free-form deep-read agent reports + corpus stats, calls Sonnet 4.6
once with a strict JSON schema, and writes 7 JSON files under
~/.claude/digital-twin/analysis/insights/. synthesize.py then renders cards
directly from those JSON files.

Architecture: the 6 Phase 5 agents return rich free-form Markdown (more nuanced
than JSON-mode narratives). This script is the *structuring* pass that turns
that prose into card-shaped data, mirroring how the built-in /insights pipeline
works.

LLM transport (in order of preference):
  1. `claude -p --model <model>` subprocess — uses user's existing auth, no key
  2. Optional Anthropic SDK fallback (`--allow-sdk-fallback` + ANTHROPIC_API_KEY)
  3. Mocked response (--mock-response-file) for tests

Outputs (one file each):
  analysis/insights/project_areas.json
  analysis/insights/interaction_style.json
  analysis/insights/big_wins.json
  analysis/insights/friction.json
  analysis/insights/suggestions.json
  analysis/insights/horizon.json
  analysis/insights/fun_ending.json

Exit codes:
  0 — success, or reports/ is empty (warn and skip — Tier 3 fallback)
  2 — reports present but the LLM call failed (synthesize.py will fall back to Tier 2)
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

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
SCHEMA_PATH = PLUGIN_ROOT / "references" / "insights-schema.json"
PROMPT_PATH = PLUGIN_ROOT / "references" / "prompts" / "insights-extraction.md"

SECTION_KEYS = (
    "project_areas",
    "interaction_style",
    "big_wins",
    "friction",
    "suggestions",
    "horizon",
    "fun_ending",
)


def load_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def load_json(path: Path, default=None):
    if not path.exists():
        return default
    try:
        with open(path, encoding="utf-8") as fp:
            return json.load(fp)
    except (OSError, json.JSONDecodeError):
        return default


def build_stats_packet(analysis_dir: Path) -> str:
    """Concatenate the four primary stats files into one trimmed JSON blob."""
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
        # Trim verbose / redundant fields to keep input token count manageable.
        if key == "convergence_pairs":
            data.pop("first_words_per_class", None)
        if key == "plan_inventory":
            data.pop("plans", None)
        if key == "numbers":
            # Keep top-20 vocab but drop full word frequency dictionary.
            data.pop("vocab", None)
        packet[key] = data
    # Memory inventory: top-level counts only, not full entries.
    mem = load_json(analysis_dir / "memory-inventory.json", default={}) or {}
    packet["memory_inventory_summary"] = {
        "n_files": mem.get("n_files"),
        "by_type": mem.get("by_type"),
        "by_project_type_top10": dict(
            list((mem.get("by_project_type") or {}).items())[:10]
        ),
        "feedback_rule_names": [
            (e.get("name") or "") for e in mem.get("entries", [])
            if e.get("type") == "feedback"
        ][:30],
    }
    return json.dumps(packet, indent=2, ensure_ascii=False)


def build_reports_packet(reports_dir: Path) -> tuple[str, list[str]]:
    """Glob all .md in reports_dir, return concatenated text + the file list."""
    files = sorted(glob(str(reports_dir / "*.md")))
    if not files:
        return "", []
    blocks = []
    for fp in files:
        name = Path(fp).name
        blocks.append(f"\n\n========== FILE: {name} ==========\n\n")
        blocks.append(load_text(Path(fp)))
    return "".join(blocks), [Path(f).name for f in files]


def fill_prompt(user_name: str, stats: str, reports: str, schema_json: str) -> str:
    tpl = load_text(PROMPT_PATH)
    if not tpl:
        raise SystemExit(f"ERROR: prompt template not found at {PROMPT_PATH}")
    return (
        tpl.replace("{{USER_NAME}}", user_name)
        .replace("{{STATS_PACKET}}", stats)
        .replace("{{REPORTS_PACKET}}", reports)
        .replace("{{SCHEMA_JSON}}", schema_json)
    )


def call_claude_cli(prompt: str, model: str, timeout: int = 900) -> str:
    """Invoke `claude -p --model <model>` and return its stdout.

    Uses the user's existing Claude Code auth (OAuth/keychain). `--bare` mode
    would force ANTHROPIC_API_KEY-only auth and fails for OAuth users, so we
    avoid it. `--no-session-persistence` keeps the call ephemeral.
    """
    if shutil.which("claude") is None:
        raise RuntimeError("claude CLI not on PATH")
    proc = subprocess.run(
        [
            "claude", "-p",
            "--model", model,
            "--output-format", "text",
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


def call_anthropic_sdk(prompt: str, model: str) -> str:
    """Optional fallback: call Anthropic SDK if ANTHROPIC_API_KEY is set."""
    try:
        import anthropic  # type: ignore
    except ImportError:
        raise RuntimeError("anthropic SDK not installed")
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise RuntimeError("ANTHROPIC_API_KEY not set")
    client = anthropic.Anthropic()
    resp = client.messages.create(
        model=model,
        max_tokens=8192,
        messages=[{"role": "user", "content": prompt}],
    )
    return "".join(
        b.text for b in resp.content if getattr(b, "type", "") == "text"
    )


JSON_OBJECT_RE = re.compile(r"\{[\s\S]*\}")


def strip_to_json(raw: str) -> str:
    """Strip code fences and chatter around a JSON object."""
    s = raw.strip()
    # Strip ```json ... ``` fences if present
    if s.startswith("```"):
        s = re.sub(r"^```(?:json)?\s*\n", "", s)
        s = re.sub(r"\n```\s*$", "", s)
        s = s.strip()
    # If there's still chatter, extract the largest {...} span
    if not s.startswith("{"):
        m = JSON_OBJECT_RE.search(s)
        if m:
            s = m.group(0)
    return s


def try_parse_with_repair(s: str) -> tuple[dict | None, str]:
    """Parse JSON, attempting common repairs if strict parse fails.

    Returns (parsed_or_None, error_msg).
    """
    try:
        return json.loads(s), ""
    except json.JSONDecodeError:
        pass

    # Repair 1: LLM emits a premature `}` closing the top-level object before
    # the last 1-2 sections (e.g. `}]}},"horizon":`). Remove the extra `}`.
    for needle, target in (
        ("}]}},\"horizon\":", "}]},\"horizon\":"),
        ("}]}},\"fun_ending\":", "}]},\"fun_ending\":"),
        ("}}},\"horizon\":", "}},\"horizon\":"),
        ("}}},\"fun_ending\":", "}},\"fun_ending\":"),
    ):
        if needle in s:
            s2 = s.replace(needle, target, 1)
            try:
                obj = json.loads(s2)
                return obj, f"repaired: removed spurious '}}' before '{target[3:]}'"
            except json.JSONDecodeError:
                continue

    # Repair 2: use raw_decode to grab the first valid object, drop trailing.
    try:
        obj, end = json.JSONDecoder().raw_decode(s)
        trailing = s[end:].strip()
        return obj, (
            f"repaired: parsed first valid object, dropped {len(trailing)} trailing chars"
        )
    except json.JSONDecodeError as e:
        return None, str(e)


REQUIRED_FIELDS = {
    "project_areas": ("array", ["slug", "count", "share", "description"]),
    "interaction_style": ("object", ["narrative_html", "key_pattern"]),
    "big_wins": ("object_with_cards", ["intro", "cards"], ["title", "description"]),
    "friction": ("object_with_cards", ["intro", "cards"], ["title", "description"]),
    "suggestions": (
        "suggestions",
        ["claude_md_additions", "features_to_try", "patterns_to_keep"],
    ),
    "horizon": (
        "object_with_cards",
        ["intro", "cards"],
        ["title", "whats_possible", "how_to_try"],
    ),
    "fun_ending": ("object", ["headline", "detail"]),
}


def validate_section(key: str, value) -> list[str]:
    """Lightweight schema check. Returns list of error strings (empty = ok)."""
    spec = REQUIRED_FIELDS.get(key)
    if not spec:
        return [f"unknown section: {key}"]
    errs: list[str] = []
    if spec[0] == "array":
        if not isinstance(value, list):
            return [f"{key}: expected array, got {type(value).__name__}"]
        for i, item in enumerate(value):
            for f in spec[1]:
                if f not in item:
                    errs.append(f"{key}[{i}].{f} missing")
    elif spec[0] == "object":
        if not isinstance(value, dict):
            return [f"{key}: expected object"]
        for f in spec[1]:
            if f not in value:
                errs.append(f"{key}.{f} missing")
    elif spec[0] == "object_with_cards":
        if not isinstance(value, dict):
            return [f"{key}: expected object"]
        for f in spec[1]:
            if f not in value:
                errs.append(f"{key}.{f} missing")
        if isinstance(value.get("cards"), list):
            for i, card in enumerate(value["cards"]):
                for f in spec[2]:
                    if f not in card:
                        errs.append(f"{key}.cards[{i}].{f} missing")
    elif spec[0] == "suggestions":
        if not isinstance(value, dict):
            return [f"{key}: expected object"]
        for f in spec[1]:
            if f not in value:
                errs.append(f"{key}.{f} missing")
            elif not isinstance(value[f], list):
                errs.append(f"{key}.{f} must be array")
    return errs


def validate_all(obj: dict) -> list[str]:
    errs: list[str] = []
    for key in SECTION_KEYS:
        if key not in obj:
            errs.append(f"missing top-level key: {key}")
            continue
        errs.extend(validate_section(key, obj[key]))
    return errs


def write_sections(obj: dict, out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for key in SECTION_KEYS:
        path = out_dir / f"{key}.json"
        with open(path, "w", encoding="utf-8") as fp:
            json.dump(obj[key], fp, indent=2, ensure_ascii=False)
        written.append(path)
    return written


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--reports-dir",
        default=os.path.expanduser("~/.claude/digital-twin/analysis/reports"),
    )
    ap.add_argument(
        "--analysis-dir",
        default=os.path.expanduser("~/.claude/digital-twin/analysis"),
    )
    ap.add_argument(
        "--insights-dir",
        default=os.path.expanduser("~/.claude/digital-twin/analysis/insights"),
    )
    ap.add_argument(
        "--user-name",
        default=os.environ.get("DIGITAL_TWIN_USER_NAME", os.environ.get("USER", "user")),
    )
    ap.add_argument("--model", default="claude-sonnet-4-6")
    ap.add_argument(
        "--mock-response-file",
        help="Path to a JSON file containing a fake LLM response. Used by tests.",
    )
    ap.add_argument(
        "--allow-sdk-fallback",
        action="store_true",
        help=(
            "If claude CLI fails, allow falling back to the Anthropic SDK using "
            "ANTHROPIC_API_KEY. Disabled by default so corpus transport stays "
            "on the user's Claude Code auth path unless explicitly requested."
        ),
    )
    ap.add_argument(
        "--save-raw",
        help="If set, write the raw LLM response to this path before parsing.",
    )
    ap.add_argument(
        "--save-prompt",
        help="If set, write the assembled prompt to this path (debugging).",
    )
    args = ap.parse_args()

    reports_dir = Path(args.reports_dir).expanduser()
    analysis_dir = Path(args.analysis_dir).expanduser()
    insights_dir = Path(args.insights_dir).expanduser()

    reports_packet, files = build_reports_packet(reports_dir)
    if not files:
        print(
            f"WARN: no .md reports found in {reports_dir}. "
            "Skipping insights extraction. synthesize.py will fall back to Tier 2.",
            file=sys.stderr,
        )
        return 0

    print(f"Loading {len(files)} report(s): {', '.join(files)}", file=sys.stderr)
    stats_packet = build_stats_packet(analysis_dir)
    schema_text = load_text(SCHEMA_PATH)
    if not schema_text:
        print(f"ERROR: schema not found at {SCHEMA_PATH}", file=sys.stderr)
        return 2

    prompt = fill_prompt(args.user_name, stats_packet, reports_packet, schema_text)
    print(f"Prompt size: {len(prompt):,} chars", file=sys.stderr)

    if args.save_prompt:
        Path(args.save_prompt).write_text(prompt, encoding="utf-8")
        print(f"Saved assembled prompt to {args.save_prompt}", file=sys.stderr)

    # Get response
    if args.mock_response_file:
        raw = load_text(Path(args.mock_response_file))
        print(
            f"Loaded mock response from {args.mock_response_file} ({len(raw):,} chars)",
            file=sys.stderr,
        )
    else:
        try:
            print(f"Calling claude -p --model {args.model} ...", file=sys.stderr)
            raw = call_claude_cli(prompt, args.model)
        except Exception as e:
            print(f"claude CLI failed: {e}", file=sys.stderr)
            if not args.allow_sdk_fallback:
                print(
                    "Anthropic SDK fallback is disabled. Re-run with "
                    "--allow-sdk-fallback to permit API-key transport.",
                    file=sys.stderr,
                )
                print(
                    "synthesize.py will fall back to Tier 2 rule-based builders.",
                    file=sys.stderr,
                )
                return 2
            print("Falling back to Anthropic SDK ...", file=sys.stderr)
            try:
                raw = call_anthropic_sdk(prompt, args.model)
            except Exception as e2:
                print(f"ERROR: Anthropic SDK also failed: {e2}", file=sys.stderr)
                print(
                    "synthesize.py will fall back to Tier 2 rule-based builders.",
                    file=sys.stderr,
                )
                return 2

    if args.save_raw:
        Path(args.save_raw).write_text(raw, encoding="utf-8")
        print(f"Saved raw LLM response to {args.save_raw}", file=sys.stderr)

    # Parse
    cleaned = strip_to_json(raw)
    obj, note = try_parse_with_repair(cleaned)
    if obj is None:
        print(f"ERROR: LLM response is not valid JSON: {note}", file=sys.stderr)
        print(f"First 500 chars of cleaned output:\n{cleaned[:500]}", file=sys.stderr)
        return 2
    if note:
        print(f"NOTE: {note}", file=sys.stderr)

    # Validate
    errs = validate_all(obj)
    if errs:
        print("ERROR: extracted JSON failed schema validation:", file=sys.stderr)
        for err in errs[:20]:
            print(f"  - {err}", file=sys.stderr)
        if len(errs) > 20:
            print(f"  ... and {len(errs)-20} more", file=sys.stderr)
        # Still write what we have so the user can inspect
        debug_path = insights_dir / "_extraction_invalid.json"
        insights_dir.mkdir(parents=True, exist_ok=True)
        with open(debug_path, "w", encoding="utf-8") as fp:
            json.dump(obj, fp, indent=2, ensure_ascii=False)
        print(f"Wrote invalid extraction for inspection: {debug_path}", file=sys.stderr)
        return 2

    written = write_sections(obj, insights_dir)
    print(f"\nWrote {len(written)} insights file(s) to {insights_dir}:", file=sys.stderr)
    for p in written:
        size = p.stat().st_size
        print(f"  {p.name} ({size:,} bytes)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
