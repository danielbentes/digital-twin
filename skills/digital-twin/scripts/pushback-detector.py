#!/usr/bin/env python3
"""
pushback-detector.py — Phase 4 of the digital-twin skill.

Watches `(assistant-turn, user-reply)` pairs in real time. When a pushback
appears that is not covered by an existing memory rule, it drafts a candidate
memory file in canonical YAML-frontmatter format and queues it at:

    ~/.claude/digital-twin/proposed-rules/

The detector is INCREMENTAL: it tracks the byte offset it last consumed in each
.jsonl session file (state at ~/.claude/digital-twin/.state.json) and only
processes new data on each run. Dedup is by content hash so re-runs are safe.

Never auto-writes to memory. Only emits proposals. The /digital-twin
propose-rules command walks the user through approve/reject/defer/edit.

Usage:
    pushback-detector.py                          # incremental scan
    pushback-detector.py --reset-state            # rescan from scratch
    pushback-detector.py --since 2026-05-01       # ignore older sessions
    pushback-detector.py --dry-run                # print, do not write

Tunables:
    --min-confidence FLOAT (default 0.4)
    --max-proposals INT    (default 25 per run, to avoid flooding)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from glob import glob
from pathlib import Path

APPROVAL_WORDS = {
    "proceed", "continue", "yes", "go", "ok", "okay", "sounds", "great",
    "perfect", "ship", "merge", "do", "lgtm", "approved",
}
EXPLICIT_PUSHBACK = {
    "stop", "wait", "no", "don't", "dont", "actually", "but", "however",
    "hold", "pause", "revert", "rollback", "halt", "abort",
}

DISSATISFACTION_MARKERS = re.compile(
    r"\b(?:but|however|actually|instead|rather than|why didn'?t|"
    r"you didn'?t|missing|forgot|incorrect|wrong|not (?:what|quite)|"
    r"hmm|that'?s not|undo|revert|let'?s try|too (?:verbose|much|long)|"
    r"isn'?t (?:right|correct)|won'?t work)\b",
    re.IGNORECASE,
)

AUTO_WAKE_PREFIXES = (
    "-\n## Paperclip", "## Paperclip", "Paperclip Wake Payload",
    "<<autonomous", "You are agent", "You are a ",
    "<<autonomous-loop", "<<autonomous-loop-dynamic>>",
    "<system-reminder>", "<command-name>",
    "Task Notification", "task notification",
    "<task-notification>", "<task-id>", "<tool-use-id>",
    "This session is being continued",
    "<local-command-",
    "[Request interrupted",
    "Caveat: The messages below",
)

# Catch-all: replies that start with an XML-style tag (e.g., <task-notification>,
# <system-reminder>, <command-name>, <local-command-stdout>) are system-injected,
# never user prompts.
SYSTEM_TAG_RE = re.compile(r"^\s*<[a-z][a-z0-9-]+>")

TOKEN_RE = re.compile(r"\b[\w'-]{2,}\b", re.UNICODE)
SENTENCE_END = re.compile(r"[.!?]\s+")


def is_auto_wake(text: str) -> bool:
    if not text:
        return True
    if SYSTEM_TAG_RE.match(text):
        return True
    head = text.lstrip().lstrip("-*>#").lstrip()[:300]
    return any(head.startswith(p) or p in head[:100] for p in AUTO_WAKE_PREFIXES)


def first_word(text: str) -> str | None:
    stripped = text.lstrip().lstrip("/-#*>").strip()
    if not stripped:
        return None
    m = TOKEN_RE.match(stripped)
    return m.group(0).lower() if m else None


def extract_text(obj: dict) -> str | None:
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


def classify(reply: str, approved_median: float) -> tuple[str, float]:
    """Return (class, confidence). Confidence in [0,1]."""
    fw = first_word(reply)
    if fw in EXPLICIT_PUSHBACK:
        return ("explicit_pushback", 0.9)
    if fw in APPROVAL_WORDS:
        return ("approval", 0.95)
    long_enough = len(reply) >= 2 * approved_median and approved_median > 0
    marker = DISSATISFACTION_MARKERS.search(reply)
    if long_enough and marker:
        # Confidence scales with length above threshold (capped)
        ratio = min(len(reply) / (approved_median * 4), 1.0)
        return ("implicit_pushback", 0.4 + 0.5 * ratio)
    return ("neutral", 0.0)


def first_sentence(text: str, max_chars: int = 200) -> str:
    text = text.strip()
    parts = SENTENCE_END.split(text, maxsplit=1)
    s = parts[0] if parts else text
    if len(s) > max_chars:
        s = s[:max_chars].rstrip() + "..."
    return s


def slugify(text: str, max_len: int = 50) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")
    return s[:max_len] or "rule"


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()[:16]


def covered_by_existing(reply: str, existing_descriptions: list[str]) -> bool:
    """
    Heuristic: if the pushback's key tokens overlap heavily with an existing
    memory description, skip it. Avoids proposing duplicates of rules the
    user already wrote.
    """
    reply_tokens = {t for t in TOKEN_RE.findall(reply.lower()) if len(t) > 4}
    if not reply_tokens:
        return False
    for desc in existing_descriptions:
        desc_tokens = {t for t in TOKEN_RE.findall(desc.lower()) if len(t) > 4}
        if not desc_tokens:
            continue
        overlap = len(reply_tokens & desc_tokens)
        if overlap >= 4 and overlap / max(len(reply_tokens), 1) > 0.3:
            return True
    return False


def project_slug(jsonl_path: str) -> str:
    parts = Path(jsonl_path).parts
    try:
        i = parts.index("projects")
        return parts[i + 1] if i + 1 < len(parts) else "unknown"
    except ValueError:
        return "unknown"


def load_existing_descriptions(projects_root: Path) -> list[str]:
    descs: list[str] = []
    for path in glob(str(projects_root / "*" / "memory" / "*.md")):
        if Path(path).name == "MEMORY.md":
            continue
        try:
            with open(path, encoding="utf-8") as fp:
                head = fp.read(2048)
        except OSError:
            continue
        m = re.search(r"^description:\s*(.+)$", head, re.MULTILINE)
        if m:
            descs.append(m.group(1).strip().strip('"').strip("'"))
    return descs


def proposal_body(reply: str, asst: str, project: str, dt_iso: str) -> tuple[str, str]:
    """Return (slug, full_markdown_for_proposal_file)."""
    summary = first_sentence(reply, 120)
    name = slugify(summary, max_len=40)
    description = first_sentence(reply, 150).replace("\n", " ")
    body = (
        f"---\n"
        f"name: {name}\n"
        f"description: {description}\n"
        f"type: feedback\n"
        f"---\n\n"
        f"<!-- AUTO-PROPOSED by digital-twin/pushback-detector on {dt_iso} -->\n"
        f"<!-- Project: {project} -->\n"
        f"<!-- Edit the rule body below before approving. -->\n\n"
        f"{first_sentence(reply, 400)}\n\n"
        f"**Why:** _Fill in the reason — what past incident or preference does this encode?_\n\n"
        f"**How to apply:** _Fill in when this rule should kick in._\n\n"
        f"---\n\n"
        f"## Evidence (from session)\n\n"
        f"**Assistant said:**\n> {first_sentence(asst, 300).replace(chr(10), ' ')}\n\n"
        f"**User replied:**\n> {first_sentence(reply, 500).replace(chr(10), ' ')}\n"
    )
    return name, body


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default=os.path.expanduser("~/.claude/projects"))
    ap.add_argument(
        "--out-dir",
        default=os.path.expanduser("~/.claude/digital-twin/proposed-rules"),
    )
    ap.add_argument(
        "--state-file",
        default=os.path.expanduser("~/.claude/digital-twin/.state.json"),
    )
    ap.add_argument(
        "--approved-median",
        type=float,
        default=0.0,
        help=(
            "Override the approved-reply median used as the implicit-pushback "
            "threshold. If 0, computed from the current scan."
        ),
    )
    ap.add_argument("--min-confidence", type=float, default=0.4)
    ap.add_argument("--max-proposals", type=int, default=25)
    ap.add_argument("--reset-state", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument(
        "--since",
        help="ISO date (YYYY-MM-DD). Ignore session files older than this.",
    )
    args = ap.parse_args()

    source = Path(args.source).expanduser()
    out_dir = Path(args.out_dir).expanduser()
    state_file = Path(args.state_file).expanduser()

    if not source.exists():
        print(f"ERROR: source not found: {source}", file=sys.stderr)
        return 2

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "archive").mkdir(exist_ok=True)
    state_file.parent.mkdir(parents=True, exist_ok=True)

    # Load state (per-file offsets + proposal content hashes seen)
    state: dict = {"offsets": {}, "seen_hashes": []}
    if state_file.exists() and not args.reset_state:
        try:
            with open(state_file, encoding="utf-8") as fp:
                state = json.load(fp)
        except (OSError, json.JSONDecodeError):
            pass
    state.setdefault("offsets", {})
    state.setdefault("seen_hashes", [])
    seen_hashes: set[str] = set(state["seen_hashes"])

    # Existing memory descriptions (for de-duplication against user's rules)
    existing_descriptions = load_existing_descriptions(source)

    since_ts: float | None = None
    if args.since:
        try:
            since_ts = datetime.fromisoformat(args.since).timestamp()
        except ValueError:
            print(f"ERROR: bad --since date: {args.since}", file=sys.stderr)
            return 2

    files = sorted(glob(str(source / "*" / "*.jsonl")))
    new_pairs: list[tuple[str, str, str, str]] = []  # (asst, reply, project, dt_iso)

    for fpath in files:
        if since_ts and os.path.getmtime(fpath) < since_ts:
            continue
        prev_offset = state["offsets"].get(fpath, 0)
        try:
            size = os.path.getsize(fpath)
        except OSError:
            continue
        if prev_offset > size:
            prev_offset = 0  # file rotated/truncated
        if prev_offset >= size:
            continue

        last_asst: str | None = None
        last_dt: str = ""
        try:
            fp = open(fpath, encoding="utf-8", errors="replace")
        except OSError:
            continue
        try:
            fp.seek(prev_offset)
            # If we resumed mid-line, drop the partial line and only resume
            # cleanly at the next newline so JSON parsing is safe.
            if prev_offset > 0:
                fp.readline()
            for line in fp:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                t = obj.get("type")
                ts = obj.get("timestamp") or obj.get("ts") or ""
                if t == "assistant":
                    text = extract_text(obj)
                    if text:
                        last_asst = text
                        last_dt = ts
                elif t == "user" and last_asst is not None:
                    reply = extract_text(obj) or ""
                    if reply and not is_auto_wake(reply):
                        new_pairs.append(
                            (last_asst, reply, project_slug(fpath), last_dt or ts)
                        )
                    last_asst = None
            state["offsets"][fpath] = fp.tell()
        finally:
            fp.close()

    if not new_pairs:
        print("No new (assistant, user) pairs since last run.")
        if not args.dry_run:
            with open(state_file, "w", encoding="utf-8") as fp:
                json.dump(state, fp, indent=2)
        return 0

    # Estimate approved-median for confidence scaling
    approved_median = args.approved_median
    if approved_median <= 0:
        approved_lens = [
            len(r) for _a, r, _p, _t in new_pairs
            if first_word(r) in APPROVAL_WORDS
        ]
        if approved_lens:
            approved_lens.sort()
            approved_median = float(approved_lens[len(approved_lens) // 2])
        else:
            # Fall back to a conservative threshold based on all replies
            all_lens = sorted(len(r) for _a, r, _p, _t in new_pairs)
            approved_median = float(all_lens[len(all_lens) // 2]) / 2 if all_lens else 50.0

    # Score, filter, dedup, emit
    candidates: list[tuple[float, str, str, str, str]] = []
    for asst, reply, project, dt_iso in new_pairs:
        cls, conf = classify(reply, approved_median)
        if cls not in ("explicit_pushback", "implicit_pushback"):
            continue
        if conf < args.min_confidence:
            continue
        if covered_by_existing(reply, existing_descriptions):
            continue
        h = content_hash(reply)
        if h in seen_hashes:
            continue
        candidates.append((conf, h, asst, reply, project + "|" + dt_iso))

    candidates.sort(key=lambda x: -x[0])
    # Dedupe within this run by content hash (keep highest-confidence)
    unique: dict[str, tuple[float, str, str, str, str]] = {}
    for cand in candidates:
        h = cand[1]
        if h not in unique:
            unique[h] = cand
    candidates = sorted(unique.values(), key=lambda x: -x[0])[: args.max_proposals]

    print(f"Scanned {len(new_pairs)} new pair(s).")
    print(f"Approved-reply median (threshold anchor): {approved_median:.0f} chars.")
    print(f"Existing rule descriptions known: {len(existing_descriptions)}.")
    print(f"Candidate proposals after filters: {len(candidates)}.")

    written = 0
    for conf, h, asst, reply, project_dt in candidates:
        project, dt_iso = (project_dt.split("|", 1) + [""])[:2]
        name, body = proposal_body(reply, asst, project, dt_iso or datetime.now(timezone.utc).isoformat())
        # Filename: confidence-prefixed for natural sort
        fname = f"{int(conf*100):03d}_{h}_{slugify(name, 30)}.md"
        out_path = out_dir / fname
        if out_path.exists():
            seen_hashes.add(h)
            continue
        print(f"  [{conf:.2f}] {fname}")
        if not args.dry_run:
            with open(out_path, "w", encoding="utf-8") as fp:
                fp.write(body)
            seen_hashes.add(h)
            written += 1

    if not args.dry_run:
        # Cap seen_hashes growth (keep newest 10k)
        state["seen_hashes"] = list(seen_hashes)[-10000:]
        with open(state_file, "w", encoding="utf-8") as fp:
            json.dump(state, fp, indent=2)

    print(f"\nWrote {written} new proposal(s) to {out_dir}")
    print("Run `/digital-twin propose-rules` to review them.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
