#!/usr/bin/env python3
"""
evaluate-twin.py — deterministic Behavioral Twin v1 eval harness.

The harness intentionally does not call an LLM. It scores saved candidate
responses against held-out expected behavior labels so CI can guard the twin's
operational shape without network/API dependencies.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

VERIFY_RE = re.compile(r"\b(test|tests|verify|verified|fresh|ci|browser|screenshot|type ?check|lint)\b", re.I)
RECOVERY_RE = re.compile(r"\b(fair pushback|you'?re right|what i claimed|actually true|gap)\b", re.I)
FILLER_RE = re.compile(r"\b(i understand|certainly|absolutely|happy to help|great question)\b", re.I)
QUESTION_RE = re.compile(r"\?")
EMOJI_RE = re.compile(r"[\U0001F300-\U0001FAFF]")


def _contains_any(text: str, values: list[str]) -> bool:
    low = text.lower()
    return any(v.lower() in low for v in values)


def score_response(response: str, expected: dict) -> dict:
    response = response.strip()
    scores = {}

    decision_keywords = expected.get("decision_keywords") or []
    scores["decision_match"] = (
        1 if not decision_keywords or _contains_any(response, decision_keywords) else 0
    )

    avoid_questions = expected.get("avoid_unnecessary_questions", False)
    scores["autonomy_match"] = 1 if not avoid_questions or not QUESTION_RE.search(response) else 0

    if expected.get("verification_required"):
        scores["verification_rigor"] = 1 if VERIFY_RE.search(response) else 0
    else:
        scores["verification_rigor"] = 1

    if expected.get("recovery_required"):
        has_recovery = bool(RECOVERY_RE.search(response))
        has_table_shape = "|" in response and ("claimed" in response.lower() or "gap" in response.lower())
        question_count = len(QUESTION_RE.findall(response))
        scores["recovery_quality"] = 1 if has_recovery and has_table_shape and question_count <= 1 else 0
    else:
        scores["recovery_quality"] = 1

    max_chars = expected.get("max_chars", 900)
    no_filler = not FILLER_RE.search(response)
    no_emoji = not EMOJI_RE.search(response)
    scores["voice_match"] = 1 if len(response) <= max_chars and no_filler and no_emoji else 0

    avoid_phrases = expected.get("avoid_phrases") or []
    scores["avoidance_match"] = 1 if not _contains_any(response, avoid_phrases) else 0
    max_score = len(scores)
    scores["total"] = sum(scores.values())
    scores["max"] = max_score
    return scores


def evaluate(cases: list[dict]) -> dict:
    rows = []
    twin_wins = 0
    trigger_hits = 0
    trigger_total = 0
    for case in cases:
        expected = case.get("expected") or {}
        twin = score_response(case.get("twin_response", ""), expected)
        generic = score_response(case.get("generic_response", ""), expected)
        if twin["total"] > generic["total"]:
            twin_wins += 1
        if expected.get("pushback_trigger"):
            trigger_total += 1
            if twin.get("avoidance_match") and twin.get("recovery_quality"):
                trigger_hits += 1
        rows.append({
            "id": case.get("id"),
            "category": case.get("category"),
            "twin": twin,
            "generic": generic,
            "winner": "twin" if twin["total"] > generic["total"] else "generic_or_tie",
        })
    n = len(cases)
    return {
        "n_cases": n,
        "twin_win_rate": round(twin_wins / n, 3) if n else 0.0,
        "pushback_trigger_hit_rate": round(trigger_hits / trigger_total, 3) if trigger_total else None,
        "rows": rows,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("cases", help="JSON file with eval cases.")
    ap.add_argument("--out-json")
    args = ap.parse_args()

    try:
        cases = json.loads(Path(args.cases).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        print(f"ERROR: could not read cases: {e}", file=sys.stderr)
        return 2
    if not isinstance(cases, list):
        print("ERROR: cases file must contain a JSON array", file=sys.stderr)
        return 2

    result = evaluate(cases)
    text = json.dumps(result, indent=2, ensure_ascii=False)
    if args.out_json:
        Path(args.out_json).write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
