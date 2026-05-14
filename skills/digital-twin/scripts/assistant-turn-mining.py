#!/usr/bin/env python3
"""
assistant-turn-mining.py — Phase 4c of the digital-twin skill.

Walks all session .jsonl files and reconstructs (assistant_turn, user_reply)
pairs. Classifies each user reply as:
  * approval        — starts with proceed/continue/yes/go/etc.
  * explicit_pushback — starts with stop/wait/no/don't/etc.
  * implicit_pushback — neutral or rephrase but with length >= 2x of the
                        approved-median (heuristic: long replies after an
                        assistant turn signal dissatisfaction even without
                        explicit pushback verbs)
  * neutral         — everything else

Computes:
  * counts of each class
  * median + p90 length per class (chars)
  * top first words per class (the lexicon of approval / pushback)
  * representative quotes (5 longest of each pushback class) — useful for
    seeding the twin's "what triggers pushback" list

Outputs:
  convergence-pairs.json — full pair counts + stats
  pushback-triggers.md  — markdown list of pushback patterns + sample quotes
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter
from glob import glob
from pathlib import Path
from typing import cast

from safe_paths import is_safe_input_file

APPROVAL_WORDS = {
    "proceed", "continue", "yes", "go", "ok", "okay", "sounds", "great",
    "perfect", "ship", "merge", "do", "👍", "lgtm", "approved",
}
EXPLICIT_PUSHBACK = {
    "stop", "wait", "no", "don't", "dont", "actually", "but", "however",
    "hold", "pause", "revert", "rollback", "halt", "abort",
}

# Markers that suggest dissatisfaction even when the first word is neutral.
# A reply must contain one of these AND be substantially long to count as
# implicit pushback. Without this guard, every long continuation gets
# classified as pushback.
DISSATISFACTION_MARKERS = re.compile(
    r"\b(?:but|however|actually|instead|rather than|why didn'?t|"
    r"you didn'?t|missing|forgot|incorrect|wrong|not (?:what|quite)|"
    r"hmm|that'?s not|undo|revert|let'?s try|too (?:verbose|much|long)|"
    r"isn'?t (?:right|correct)|won'?t work)\b",
    re.IGNORECASE,
)

TOKEN_RE = re.compile(r"\b[\w'-]{2,}\b", re.UNICODE)
AUTO_WAKE_PREFIXES = (
    "-\n## Paperclip", "## Paperclip", "Paperclip Wake Payload",
    "<<autonomous", "You are agent",
)


def is_auto_wake(text: str) -> bool:
    if not text:
        return True
    return any(text.startswith(p) for p in AUTO_WAKE_PREFIXES)


def first_word(text: str) -> str | None:
    stripped = text.lstrip().lstrip("/-#*>").strip()
    if not stripped:
        return None
    m = TOKEN_RE.match(stripped)
    return m.group(0).lower() if m else None


def extract_text(obj: dict) -> str | None:
    """Pull text out of an assistant or user entry."""
    msg = obj.get("message", {})
    content = msg.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
        return "\n".join(p for p in parts if p) or None
    return None


def percentile(values: list[int], q: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    k = (len(s) - 1) * q
    f = int(k)
    c = min(f + 1, len(s) - 1)
    if f == c:
        return float(s[f])
    return s[f] + (s[c] - s[f]) * (k - f)


def classify_reply(reply: str, approved_median: float) -> str:
    fw = first_word(reply)
    if fw in APPROVAL_WORDS:
        return "approval"
    if fw in EXPLICIT_PUSHBACK:
        return "explicit_pushback"
    # Implicit pushback: long AND contains a dissatisfaction marker.
    # Length-only would flag every substantive continuation as pushback.
    long_enough = (
        len(reply) >= 2 * approved_median and approved_median > 0
    )
    if long_enough and DISSATISFACTION_MARKERS.search(reply):
        return "implicit_pushback"
    return "neutral"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--source",
        default=os.path.expanduser("~/.claude/projects"),
    )
    ap.add_argument(
        "--out-json",
        default=os.path.expanduser(
            "~/.claude/digital-twin/analysis/convergence-pairs.json"
        ),
    )
    ap.add_argument(
        "--out-md",
        default=os.path.expanduser(
            "~/.claude/digital-twin/analysis/pushback-triggers.md"
        ),
    )
    ap.add_argument(
        "--sample-quotes",
        type=int,
        default=10,
        help="How many representative quotes to surface per class.",
    )
    args = ap.parse_args()

    source = Path(args.source).expanduser()
    if not source.exists():
        print(f"ERROR: source not found: {source}", file=sys.stderr)
        return 2

    out_json = Path(args.out_json).expanduser()
    out_md = Path(args.out_md).expanduser()
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_md.parent.mkdir(parents=True, exist_ok=True)

    # Pass 1: collect raw pairs (no classification yet — need approved_median first)
    raw_pairs: list[tuple[str, str]] = []  # (asst_text, user_text)
    files = [
        f for f in sorted(glob(str(source / "*" / "*.jsonl")))
        if is_safe_input_file(f, source)
    ]
    for fpath in files:
        last_asst: str | None = None
        try:
            fp = open(fpath, encoding="utf-8", errors="replace")
        except OSError:
            continue
        try:
            for line in fp:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                t = obj.get("type")
                if t == "assistant":
                    text = extract_text(obj)
                    if text:
                        last_asst = text
                elif t == "user" and last_asst is not None:
                    reply = extract_text(obj) or ""
                    if reply and not is_auto_wake(reply):
                        raw_pairs.append((last_asst, reply))
                    last_asst = None
        finally:
            fp.close()

    if not raw_pairs:
        print("ERROR: no (assistant, user) pairs found", file=sys.stderr)
        return 2

    # First pass: compute approved median to anchor implicit-pushback threshold.
    approved_lengths_pass1 = [
        len(reply) for _a, reply in raw_pairs if first_word(reply) in APPROVAL_WORDS
    ]
    approved_median_pass1 = percentile(approved_lengths_pass1, 0.5)
    if approved_median_pass1 <= 0:
        # Fallback if no approvals: use median of all replies / 2
        approved_median_pass1 = percentile([len(r) for _, r in raw_pairs], 0.5) / 2

    # Second pass: classify
    counts: Counter[str] = Counter()
    lengths_by_class: dict[str, list[int]] = {
        "approval": [], "explicit_pushback": [], "implicit_pushback": [],
        "neutral": [],
    }
    first_words_by_class: dict[str, Counter[str]] = {
        "approval": Counter(), "explicit_pushback": Counter(),
        "implicit_pushback": Counter(), "neutral": Counter(),
    }
    longest_by_class: dict[str, list[tuple[int, str]]] = {
        "explicit_pushback": [], "implicit_pushback": [],
    }
    for _asst, reply in raw_pairs:
        cls = classify_reply(reply, approved_median_pass1)
        counts[cls] += 1
        lengths_by_class[cls].append(len(reply))
        fw = first_word(reply)
        if fw:
            first_words_by_class[cls][fw] += 1
        if cls in longest_by_class:
            longest_by_class[cls].append((len(reply), reply))

    stats = {
        "n_pairs": len(raw_pairs),
        "counts": dict(counts),
        "median_length_chars": {
            cls: percentile(lens, 0.5) for cls, lens in lengths_by_class.items()
        },
        "p90_length_chars": {
            cls: percentile(lens, 0.9) for cls, lens in lengths_by_class.items()
        },
        "ratio_pushback_to_approval_length": (
            round(
                percentile(
                    lengths_by_class["explicit_pushback"]
                    + lengths_by_class["implicit_pushback"],
                    0.5,
                )
                / percentile(lengths_by_class["approval"], 0.5),
                2,
            )
            if lengths_by_class["approval"]
            else None
        ),
        "first_word_top": {
            cls: cnt.most_common(20)
            for cls, cnt in first_words_by_class.items()
        },
    }

    with open(out_json, "w", encoding="utf-8") as fp:
        json.dump(stats, fp, indent=2, ensure_ascii=False)

    md = []
    md.append("# Convergence & Pushback Analysis (auto-generated)\n")
    md.append(f"- **Total (assistant, user) pairs:** {len(raw_pairs):,}")
    md.append(f"- **Approval:** {counts.get('approval', 0):,}")
    md.append(f"- **Explicit pushback:** {counts.get('explicit_pushback', 0):,}")
    md.append(f"- **Implicit pushback:** {counts.get('implicit_pushback', 0):,}")
    md.append(f"- **Neutral:** {counts.get('neutral', 0):,}")
    md.append("")
    md.append("## Median reply length by class\n")
    md.append("| Class | Median chars | p90 chars |")
    md.append("| --- | ---: | ---: |")
    median_lengths = cast(dict[str, float], stats["median_length_chars"])
    p90_lengths = cast(dict[str, float], stats["p90_length_chars"])
    for cls in ("approval", "explicit_pushback", "implicit_pushback", "neutral"):
        md.append(
            f"| {cls} | {median_lengths[cls]:.0f} | "
            f"{p90_lengths[cls]:.0f} |"
        )
    md.append("")
    if stats["ratio_pushback_to_approval_length"]:
        md.append(
            f"**Pushback replies are {stats['ratio_pushback_to_approval_length']}× "
            "longer than approval replies (median).**\n"
        )

    md.append("## Top first words by class\n")
    for cls in ("approval", "explicit_pushback", "implicit_pushback", "neutral"):
        md.append(f"### {cls}\n")
        md.append("| Word | Count |")
        md.append("| --- | ---: |")
        for w, c in first_words_by_class[cls].most_common(15):
            md.append(f"| {w} | {c} |")
        md.append("")

    md.append("## Representative pushback quotes\n")
    md.append(
        "_The longest pushback replies are the highest-signal examples of what "
        "triggers correction. Use these to seed the twin's NEVER list._\n"
    )
    for cls in ("explicit_pushback", "implicit_pushback"):
        md.append(f"### {cls}\n")
        for length, text in sorted(longest_by_class[cls], reverse=True)[
            : args.sample_quotes
        ]:
            preview = text.replace("\n", " ")
            if len(preview) > 500:
                preview = preview[:500] + "…"
            md.append(f"- ({length} chars) > {preview}")
        md.append("")

    with open(out_md, "w", encoding="utf-8") as fp:
        fp.write("\n".join(md))

    print(f"Wrote: {out_json}")
    print(f"Wrote: {out_md}")
    print("\nQuick summary:")
    print(f"  pairs:    {len(raw_pairs):,}")
    print(f"  approval: {counts.get('approval', 0):,}")
    print(f"  expl PB:  {counts.get('explicit_pushback', 0):,}")
    print(f"  impl PB:  {counts.get('implicit_pushback', 0):,}")
    if stats["ratio_pushback_to_approval_length"]:
        print(
            f"  PB:approval length ratio (median): "
            f"{stats['ratio_pushback_to_approval_length']}×"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
