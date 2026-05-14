#!/usr/bin/env python3
"""
extract-corpus.py — Phase 2 of the digital-twin skill.

Walks the user's Claude Code session logs (~/.claude/projects/*/*.jsonl by
default) and produces 4 normalized corpus files plus a summary.

Outputs (in --out directory):
  corpus.jsonl            — prompt-bearing entries, preferring full `user`
                            messages over truncated `last-prompt` cache rows
  first-prompts.jsonl     — first prompt of each session
  human-first.jsonl       — long, high-signal real human-typed first prompts
                            (excludes auto-wake payloads from heartbeat systems)
  timestamped.jsonl       — prompts with timestamps (for temporal analysis)
  _summary.json           — file/prompt/project counts + per-project breakdown

Filters:
  * Paperclip auto-wakes (and similar heartbeat patterns) are EXCLUDED from
    human-first.jsonl but KEPT in corpus.jsonl. The signatures we filter are
    documented in references/extraction-schema.md.
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

# Heuristic prefixes that mark automated wake payloads, not human prompts.
# Keep this list aligned with references/extraction-schema.md.
AUTO_WAKE_PREFIXES = (
    "-\n## Paperclip",
    "## Paperclip",
    "Paperclip Wake Payload",
    "<<autonomous",
    "You are agent",
    "<<autonomous-loop",
    "<<autonomous-loop-dynamic>>",
)

# Minimum chars for a prompt to count as "high signal real human" first prompt.
HUMAN_FIRST_MIN_CHARS = 80


def normalize_prompt_for_dedup(text: str) -> str:
    """Collapse whitespace so cache rows can be matched to full user messages."""
    return re.sub(r"\s+", " ", text or "").strip()


def is_duplicate_last_prompt(last_prompt: str, full_prompt: str) -> bool:
    """
    Return True when a lossy `last-prompt` row represents the same turn as a full
    `user`/`human` message.

    Claude Code's `last-prompt` rows are cache/analytics entries. They are often
    truncated, but they are not guaranteed to correspond to every full user turn.
    Be conservative: drop the cache row only for an exact match or a clear
    truncation-prefix match.
    """
    cached = normalize_prompt_for_dedup(last_prompt)
    full = normalize_prompt_for_dedup(full_prompt)
    if not cached or not full:
        return False
    if cached == full:
        return True

    trimmed = cached.rstrip(".… ")
    return len(trimmed) >= 40 and full.startswith(trimmed)


def is_auto_wake(text: str) -> bool:
    if not text:
        return True
    for p in AUTO_WAKE_PREFIXES:
        if text.startswith(p):
            return True
    return False


def project_slug(path: str) -> str:
    """Extract project slug from /.../.claude/projects/<slug>/<uuid>.jsonl"""
    parts = Path(path).parts
    try:
        i = parts.index("projects")
        return parts[i + 1] if i + 1 < len(parts) else "unknown"
    except ValueError:
        return "unknown"


def iter_entries(jsonl_path: str):
    """Yield (line_number, parsed_obj) for valid JSON lines, skip bad lines."""
    with open(jsonl_path, encoding="utf-8", errors="replace") as fp:
        for ln, line in enumerate(fp, 1):
            line = line.strip()
            if not line:
                continue
            try:
                yield ln, json.loads(line)
            except json.JSONDecodeError:
                continue


def extract_prompt(obj: dict) -> tuple[str | None, str | None]:
    """
    Return (text, timestamp_iso) for a prompt-bearing entry, or (None, None).
    Handles three shapes:
      * type=last-prompt, lastPrompt=<truncated text>, timestamp=<iso>
      * type=user, message.content=<text or list of blocks>
      * type=user with role=user and content array containing text blocks
    """
    t = obj.get("type")
    ts = obj.get("timestamp")

    if t == "last-prompt":
        text = obj.get("lastPrompt", "")
        return (text if text else None), ts

    if t == "user":
        msg = obj.get("message", {})
        content = msg.get("content")
        if isinstance(content, str):
            return content, ts
        if isinstance(content, list):
            parts = []
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    parts.append(block.get("text", ""))
                elif isinstance(block, str):
                    parts.append(block)
            joined = "\n".join(p for p in parts if p)
            return (joined if joined else None), ts

    if t == "human":
        content = obj.get("content") or obj.get("text")
        if isinstance(content, str):
            return content, ts

    return None, None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--source",
        default=os.path.expanduser("~/.claude/projects"),
        help="Root directory of Claude Code session logs.",
    )
    ap.add_argument(
        "--out",
        default=os.path.expanduser("~/.claude/digital-twin/corpora"),
        help="Output directory for corpus jsonl files.",
    )
    ap.add_argument(
        "--count-only",
        action="store_true",
        help="Don't write any output, just print summary counts.",
    )
    ap.add_argument(
        "--min-files-warn",
        type=int,
        default=10,
        help="Warn if fewer than N session files are found.",
    )
    ap.add_argument(
        "--min-prompts-warn",
        type=int,
        default=500,
        help="Warn if fewer than N user-typed prompts are found.",
    )
    args = ap.parse_args()

    source = Path(args.source).expanduser()
    out = Path(args.out).expanduser()

    if not source.exists():
        print(f"ERROR: source directory does not exist: {source}", file=sys.stderr)
        return 2

    files = sorted(glob(str(source / "*" / "*.jsonl")))
    if not files:
        print(f"ERROR: no .jsonl files found under {source}", file=sys.stderr)
        return 2

    if not args.count_only:
        out.mkdir(parents=True, exist_ok=True)

    corpus_path = out / "corpus.jsonl"
    first_path = out / "first-prompts.jsonl"
    human_first_path = out / "human-first.jsonl"
    timestamped_path = out / "timestamped.jsonl"
    summary_path = out / "_summary.json"

    project_counts: Counter[str] = Counter()
    total_prompts = 0
    total_first = 0
    total_human_first = 0
    total_timestamped = 0
    total_auto_wake = 0
    source_type_counts: Counter[str] = Counter()

    corpus_fp = (
        open(corpus_path, "w", encoding="utf-8") if not args.count_only else None
    )
    first_fp = (
        open(first_path, "w", encoding="utf-8") if not args.count_only else None
    )
    human_first_fp = (
        open(human_first_path, "w", encoding="utf-8") if not args.count_only else None
    )
    timestamped_fp = (
        open(timestamped_path, "w", encoding="utf-8") if not args.count_only else None
    )

    try:
        for fpath in files:
            slug = project_slug(fpath)
            session_id = Path(fpath).stem
            seen_first = False
            prompt_entries = []

            for _ln, obj in iter_entries(fpath):
                text, ts = extract_prompt(obj)
                if not text:
                    continue
                prompt_entries.append((obj, text, ts))

            # Prefer full user/human messages over truncated last-prompt cache
            # rows only when the cache row is the same turn. Mixed sessions can
            # contain unmatched cache rows; keep those as evidence instead of
            # dropping them at session scope.
            full_prompt_texts = [
                text
                for obj, text, _ts in prompt_entries
                if obj.get("type") in {"user", "human"}
            ]
            if full_prompt_texts:
                deduped_entries = []
                for obj, text, ts in prompt_entries:
                    if obj.get("type") == "last-prompt" and any(
                        is_duplicate_last_prompt(text, full) for full in full_prompt_texts
                    ):
                        continue
                    deduped_entries.append((obj, text, ts))
                prompt_entries = deduped_entries

            for obj, text, ts in prompt_entries:
                source_type = obj.get("type") or "unknown"
                source_type_counts[source_type] += 1

                # Skip auto-wake noise from human-first counts but log to corpus.
                auto = is_auto_wake(text)
                if auto:
                    total_auto_wake += 1
                is_human = not auto

                project_counts[slug] += 1
                total_prompts += 1

                record = {
                    "project": slug,
                    "session": session_id,
                    "type": source_type,
                    "source_type": source_type,
                    "is_auto_wake": auto,
                    "is_human_typed": is_human,
                    "text": text,
                    "ts": ts,
                }
                if corpus_fp:
                    corpus_fp.write(json.dumps(record, ensure_ascii=False) + "\n")

                if ts and timestamped_fp:
                    timestamped_fp.write(
                        json.dumps(record, ensure_ascii=False) + "\n"
                    )
                if ts:
                    total_timestamped += 1

                if not seen_first:
                    if first_fp:
                        first_fp.write(
                            json.dumps(record, ensure_ascii=False) + "\n"
                        )
                    total_first += 1
                    if (
                        not auto
                        and len(text) >= HUMAN_FIRST_MIN_CHARS
                        and human_first_fp
                    ):
                        human_first_fp.write(
                            json.dumps(record, ensure_ascii=False) + "\n"
                        )
                        total_human_first += 1
                    elif (
                        not auto and len(text) >= HUMAN_FIRST_MIN_CHARS
                    ):
                        total_human_first += 1
                    seen_first = True
    finally:
        for fp in (corpus_fp, first_fp, human_first_fp, timestamped_fp):
            if fp:
                fp.close()

    summary = {
        "source": str(source),
        "out": str(out),
        "n_session_files": len(files),
        "n_prompts_total": total_prompts,
        "n_prompts_auto_wake": total_auto_wake,
        "n_prompts_human": total_prompts - total_auto_wake,
        "n_prompts_by_source_type": dict(source_type_counts),
        "n_first_prompts": total_first,
        "n_human_first_prompts": total_human_first,
        "n_timestamped": total_timestamped,
        "n_projects": len(project_counts),
        "projects": [
            {"slug": k, "n_prompts": v}
            for k, v in project_counts.most_common()
        ],
    }

    if not args.count_only:
        with open(summary_path, "w", encoding="utf-8") as fp:
            json.dump(summary, fp, indent=2, ensure_ascii=False)

    # User-facing summary
    print(f"Session files: {len(files)}")
    print(f"Total prompts: {total_prompts:,}")
    print(f"  - auto-wake (excluded from human-first): {total_auto_wake:,}")
    print(f"  - human-typed estimate: {total_prompts - total_auto_wake:,}")
    print(f"  - by source type: {dict(source_type_counts)}")
    print(f"First prompts: {total_first:,}")
    print(f"Human first prompts (>= {HUMAN_FIRST_MIN_CHARS} chars): {total_human_first:,}")
    print(f"Timestamped prompts: {total_timestamped:,}")
    print(f"Projects with prompts: {len(project_counts)}")

    if len(files) < args.min_files_warn:
        print(
            f"\nWARNING: only {len(files)} session files found "
            f"(threshold {args.min_files_warn}). Corpus may be too small for "
            "high-signal analysis."
        )
    human_count = total_prompts - total_auto_wake
    if human_count < args.min_prompts_warn:
        print(
            f"\nWARNING: only {human_count:,} human-typed prompts found "
            f"(threshold {args.min_prompts_warn:,}). Skill recommends waiting "
            "until corpus grows."
        )

    if not args.count_only:
        print(f"\nWrote: {corpus_path}")
        print(f"Wrote: {first_path}")
        print(f"Wrote: {human_first_path}")
        print(f"Wrote: {timestamped_path}")
        print(f"Wrote: {summary_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
