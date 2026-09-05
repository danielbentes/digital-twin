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
    pushback-detector.py --hook-stdin             # PostToolUse hook mode:
                                                  #   reads the hook payload JSON
                                                  #   from stdin and processes only
                                                  #   its transcript_path. There is
                                                  #   NO fallback to manual discovery.
    pushback-detector.py --initialize-offsets     # baseline missing offsets for
                                                  # existing session files at each
                                                  # file's last newline-terminated
                                                  # record. Classifies no history
                                                  # and creates no proposals.

Identity & rewrite detection
-----------------------------
All per-file state (offsets, pending assistant entries, replacement
signatures, fingerprints) is keyed by the CANONICAL absolute path of the
transcript (realpath), consistently across initialization, hook, and manual
modes. Lexical discovery aliases (e.g. /var vs /private/var) therefore never
replay history.

To bound per-turn latency, fingerprinting covers only the leading
LEADING_FINGERPRINT_WINDOW bytes and the TAIL_FINGERPRINT_WINDOW bytes of the
consumed region, with covered ranges persisted in state. A same-size rewrite
that preserves the leading window but replaces the trailing assistant record
is detected (via the tail fingerprint) before an appended user record can
cross-pair with stale text; on detection the stale pending/replacement state
is discarded and the file is rebaselined WITHOUT classifying replaced
history. Rewrites confined strictly to the uncovered middle region of a
transcript larger than the sum of both windows are NOT deterministically
detected; this residual identity limitation is documented rather than
claimed away.

Tunables:
    --min-confidence FLOAT (default 0.4)
    --max-proposals INT    (default 25 per run, to avoid flooding)
"""
from __future__ import annotations

import argparse
import contextlib
import fcntl
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone
from glob import glob
from pathlib import Path

from safe_paths import is_safe_input_file

APPROVAL_WORDS = {
    "proceed", "continue", "yes", "go", "ok", "okay", "great",
    "perfect", "ship", "merge", "do", "lgtm", "approved",
}
# "sounds" alone is ambiguous (sounds good vs. sounds wrong), so require a
# two-token confirmation pattern at the head of the reply.
SOUNDS_APPROVAL_RE = re.compile(
    r"^\s*sounds\s+(?:good|right|fine|great|reasonable|like a plan)\b",
    re.IGNORECASE,
)
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
    if fw == "sounds" and SOUNDS_APPROVAL_RE.match(reply):
        return ("approval", 0.9)
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
        if not is_safe_input_file(path, projects_root):
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


SCAFFOLD_SECTION_HEADERS = (
    "Underlying principle",
    "Rationale",
    "Applies when",
    "Does not apply when",
    "Failure mode",
    "Trust/delegation implication",
)


def proposal_ready_for_approval(body: str) -> tuple[bool, list[str]]:
    """Return (is_ready, missing_or_unfilled_sections) for a proposal body.

    A proposal is ready for approval when every scaffold section header is
    present AND its line no longer contains the `_Fill in ..._` placeholder.
    Used by /digital-twin:propose-rules and by tests that guard the guard.
    """
    missing: list[str] = []
    for header in SCAFFOLD_SECTION_HEADERS:
        pattern = re.compile(
            rf"^\*\*{re.escape(header)}:\*\*\s*(.+)$",
            re.MULTILINE,
        )
        match = pattern.search(body)
        if not match:
            missing.append(f"{header} (section missing)")
            continue
        line = match.group(1).strip()
        if not line or line.startswith("_Fill in") or line == "_":
            missing.append(f"{header} (unfilled scaffold)")
    return (not missing, missing)


def proposal_body(reply: str, asst: str, project: str, dt_iso: str) -> tuple[str, str]:
    """Return (slug, full_markdown_for_proposal_file)."""
    summary = first_sentence(reply, 120)
    base_slug = slugify(summary, max_len=32)
    # Append a short content-hash suffix so two proposals built from the same
    # leading sentence (or empty/no-alphanum replies that collapse to "rule")
    # do not collide on the frontmatter `name:` field used by memory dedup.
    hash_suffix = content_hash(reply)[:8]
    name = f"{base_slug}_{hash_suffix}"
    description = first_sentence(reply, 150).replace("\n", " ")
    body = (
        f"---\n"
        f"name: {name}\n"
        f"description: {description}\n"
        f"type: feedback\n"
        f"---\n\n"
        f"<!-- AUTO-PROPOSED by digital-twin/pushback-detector on {dt_iso} -->\n"
        f"<!-- Project: {project} -->\n"
        f"<!-- Edit the correction below before approving. -->\n\n"
        f"## Judgment correction\n\n"
        f"{first_sentence(reply, 400)}\n\n"
        f"**Underlying principle:** _Fill in the transferable judgment this correction teaches._\n\n"
        f"**Rationale:** _Fill in why this matters for acting as the user would._\n\n"
        f"**Applies when:** _Fill in the situations where this principle should kick in._\n\n"
        f"**Does not apply when:** _Fill in boundaries so the twin does not overgeneralize._\n\n"
        f"**Failure mode:** _Fill in what the agent did wrong here._\n\n"
        f"**Trust/delegation implication:** _Fill in whether this changes when to trust, interrupt, brief, or redirect other agents._\n\n"
        f"---\n\n"
        f"## Evidence (from session)\n\n"
        f"**Assistant said:**\n> {first_sentence(asst, 300).replace(chr(10), ' ')}\n\n"
        f"**User replied:**\n> {first_sentence(reply, 500).replace(chr(10), ' ')}\n"
    )
    return name, body


STATE_VERSION = 2
HOOK_EVENT_NAME = "PostToolUse"
LEADING_FINGERPRINT_WINDOW = 65536
TAIL_FINGERPRINT_WINDOW = 65536
BACKWARD_SEEK_CHUNK = 8192
MAX_BACKWARD_TAIL_BYTES = 1 << 20  # cap for last-newline search on newline-free files
MAX_BACKLOG_ENTRIES = 200  # durable spill bound for candidates past --max-proposals


class StateError(Exception):
    """Raised when persisted detector state is invalid; callers must fail closed."""


def canonical_path(path: object) -> str:
    """Canonical absolute identity for a path (realpath)."""
    return os.path.realpath(os.path.abspath(os.path.expanduser(str(path))))


def _require_type(value: object, expected: type, where: str) -> None:
    if expected is int and isinstance(value, bool):
        raise StateError(f"state field {where} must be an integer")
    if not isinstance(value, expected):
        raise StateError(
            f"state field {where} must be {expected.__name__}, "
            f"got {type(value).__name__}"
        )


def validate_state(loaded: object) -> dict:
    """Validate the typed shape of a loaded state object; raise StateError on any
    invalid typed field. Unknown fields are allowed for forward compatibility."""
    if not isinstance(loaded, dict):
        raise StateError("state file does not contain a JSON object")
    offsets = loaded.get("offsets", {})
    _require_type(offsets, dict, "offsets")
    for key, value in offsets.items():
        _require_type(key, str, "offsets key")
        _require_type(value, int, f"offsets[{key!r}]")
        if value < 0:
            raise StateError(f"state field offsets[{key!r}] must be >= 0")
    seen = loaded.get("seen_hashes", [])
    _require_type(seen, list, "seen_hashes")
    for i, h in enumerate(seen):
        _require_type(h, str, f"seen_hashes[{i}]")
    pending = loaded.get("pending", {})
    _require_type(pending, dict, "pending")
    for key, entry in pending.items():
        _require_type(key, str, "pending key")
        _require_type(entry, dict, f"pending[{key!r}]")
        for field, typ in (
            ("assistant", str),
            ("timestamp", str),
            ("start", int),
            ("end", int),
            ("sig", str),
        ):
            if field in entry:
                _require_type(entry[field], typ, f"pending[{key!r}].{field}")
    fingerprints = loaded.get("fingerprints", {})
    _require_type(fingerprints, dict, "fingerprints")
    for key, per_file in fingerprints.items():
        _require_type(key, str, "fingerprints key")
        _require_type(per_file, dict, f"fingerprints[{key!r}]")
        for part in ("leading", "tail"):
            if part not in per_file:
                continue
            meta = per_file[part]
            _require_type(meta, dict, f"fingerprints[{key!r}].{part}")
            for field, typ in (("start", int), ("end", int), ("sha256", str)):
                if field in meta:
                    _require_type(meta[field], typ, f"fingerprints[{key!r}].{part}.{field}")
    return loaded


def load_state(state_file: Path, reset: bool = False) -> dict:
    """Load detector state, FAILING CLOSED on unreadable/non-object/invalid-typed
    state. Never silently continues from an empty state, which would replay
    history."""
    state: dict = {
        "version": STATE_VERSION,
        "offsets": {},
        "seen_hashes": [],
        "pending": {},
        "fingerprints": {},
    }
    if state_file.exists() and not reset:
        try:
            with open(state_file, encoding="utf-8") as fp:
                loaded = json.load(fp)
        except (OSError, json.JSONDecodeError) as exc:
            raise StateError(
                f"state file {state_file} contains invalid JSON ({exc}); "
                "refusing to continue from empty state because that would replay history"
            )
        if not isinstance(loaded, dict):
            raise StateError(
                f"state file {state_file} does not contain a JSON object; "
                "refusing to continue from empty state because that would replay history"
            )
        validate_state(loaded)
        # Preserve unknown fields for forward compatibility.
        state.update(loaded)
    for key, default in (
        ("offsets", {}),
        ("seen_hashes", []),
        ("pending", {}),
        ("fingerprints", {}),
    ):
        state.setdefault(key, default)
    state.setdefault("version", STATE_VERSION)
    return state


def atomic_write_json(path: Path, obj: dict) -> None:
    """Publish state via an fsynced temporary file plus atomic replacement."""
    tmp = path.with_name(path.name + f".tmp.{os.getpid()}")
    try:
        with open(tmp, "w", encoding="utf-8") as fp:
            json.dump(obj, fp, indent=2)
            fp.flush()
            os.fsync(fp.fileno())
        os.replace(tmp, path)
        dir_fd = os.open(str(path.parent), os.O_RDONLY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


@contextlib.contextmanager
def state_lock(state_file: Path):
    """Serialize state access across initialization, hook, and manual runs."""
    lock_path = Path(str(state_file) + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def last_complete_newline_offset(path: str) -> int:
    """Return the byte offset just past the final newline-terminated record by
    seeking backward from EOF in bounded chunks. Never reads the whole file."""
    size = os.path.getsize(path)
    if size == 0:
        return 0
    tail = b""
    pos = size
    with open(path, "rb") as fp:
        while pos > 0:
            step = min(BACKWARD_SEEK_CHUNK, pos)
            pos -= step
            fp.seek(pos)
            data = fp.read(step) + tail
            idx = data.rfind(b"\n")
            if idx != -1:
                return pos + idx + 1
            if len(tail) + step > MAX_BACKWARD_TAIL_BYTES:
                break
            tail = data
    return 0  # no newline-terminated record found


def region_digest(path: str, start: int, end: int) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fp:
        fp.seek(start)
        remaining = end - start
        while remaining > 0:
            block = fp.read(min(65536, remaining))
            if not block:
                break
            h.update(block)
            remaining -= len(block)
    return h.hexdigest()


def update_fingerprints(path: str, key: str, state: dict, offset: int) -> None:
    fps = state.setdefault("fingerprints", {})
    if offset <= 0:
        fps.pop(key, None)
        return
    lead_end = min(offset, LEADING_FINGERPRINT_WINDOW)
    tail_start = max(0, offset - TAIL_FINGERPRINT_WINDOW)
    fps[key] = {
        "leading": {"start": 0, "end": lead_end, "sha256": region_digest(path, 0, lead_end)},
        "tail": {
            "start": tail_start,
            "end": offset,
            "sha256": region_digest(path, tail_start, offset),
        },
    }


def fingerprints_match(path: str, offset: int, fps: dict) -> bool:
    """Verify persisted fingerprints over their recorded ranges. Returns False on
    any mismatch (rewrite of consumed bytes detected)."""
    size = os.path.getsize(path)
    if offset > size:
        return False
    for part in ("leading", "tail"):
        meta = fps.get(part)
        if not isinstance(meta, dict):
            continue
        s = meta.get("start")
        e = meta.get("end")
        d = meta.get("sha256")
        if (
            isinstance(s, bool)
            or isinstance(e, bool)
            or not isinstance(s, int)
            or not isinstance(e, int)
            or not isinstance(d, str)
        ):
            continue
        if s < 0 or e > size or e <= s:
            continue
        if region_digest(path, s, e) != d:
            return False
    return True


def scan_file(path: str, key: str, state: dict) -> tuple[list, int, str | None]:
    """Consume new COMPLETE records from `path` (canonical key `key`), pairing
    them with any pending assistant entry stored in state. Mutates state.
    Returns (pairs, corrupt_lines, note). Offsets only ever advance to complete
    newline-terminated record boundaries, so a partial trailing record is never
    consumed or counted."""
    try:
        size = os.path.getsize(path)
    except OSError as exc:
        print(f"WARN: could not stat {path}: {exc}", file=sys.stderr)
        return [], 0, None
    prev = state["offsets"].get(key, 0)
    if isinstance(prev, bool) or not isinstance(prev, int) or prev < 0:
        prev = 0
    if prev > size:
        # Truncation or same-path replacement with shorter content: discard
        # stale pending pairing and rebaseline WITHOUT classifying history.
        boundary = last_complete_newline_offset(path)
        state["offsets"][key] = boundary
        state["pending"].pop(key, None)
        update_fingerprints(path, key, state, boundary)
        return [], 0, (
            f"detected truncation/replacement of {key}; discarded stale pending "
            "state and rebaselined without classifying replaced history"
        )
    fps = state.get("fingerprints", {}).get(key)
    if prev > 0 and isinstance(fps, dict) and not fingerprints_match(path, prev, fps):
        # Same-size rewrite (or other mutation) of already-consumed bytes:
        # discard ALL stale per-file pending/replacement state and rebaseline
        # WITHOUT classifying the replaced history.
        boundary = last_complete_newline_offset(path)
        state["offsets"][key] = boundary
        state["pending"].pop(key, None)
        update_fingerprints(path, key, state, boundary)
        return [], 0, (
            f"detected rewrite of already-consumed bytes in {key}; discarded stale "
            "pending/replacement state and rebaselined without classifying replaced history"
        )
    if prev >= size:
        return [], 0, None

    pairs: list[tuple[str, str, str, str]] = []
    corrupt = 0
    with open(path, "rb") as fp:
        off = prev
        if prev > 0:
            fp.seek(prev - 1)
            if fp.read(1) != b"\n":
                # Resuming mid-line (legacy offset): skip the partial line.
                off = prev - 1 + len(fp.readline())
        fp.seek(off)
        pend = state.get("pending", {}).get(key)
        if isinstance(pend, dict) and isinstance(pend.get("assistant"), str):
            last_asst: str | None = pend["assistant"]
            ts0 = pend.get("timestamp", "")
            last_dt = ts0 if isinstance(ts0, str) else ""
        else:
            last_asst = None
            last_dt = ""
        last_start = off
        last_end = off
        for line in fp:
            start = off
            off += len(line)
            if not line.endswith(b"\n"):
                # Partial trailing record: not consumed; offset stays at the
                # last complete boundary.
                off = start
                break
            stripped = line.strip()
            if not stripped:
                continue
            try:
                obj = json.loads(stripped.decode("utf-8", errors="replace"))
            except ValueError as exc:
                raise StateError(
                    f"malformed complete JSONL record in {key} at byte offset "
                    f"{start}: {exc}; refusing to advance past it"
                )
            t = obj.get("type")
            ts = obj.get("timestamp") or obj.get("ts") or ""
            if not isinstance(ts, str):
                ts = ""
            if t == "assistant":
                text = extract_text(obj)
                if text:
                    last_asst = text
                    last_dt = ts
                    last_start = start
                    last_end = off
            elif t == "user" and last_asst is not None:
                reply = extract_text(obj) or ""
                if reply and not is_auto_wake(reply):
                    pairs.append((last_asst, reply, project_slug(key), last_dt or ts))
                last_asst = None

    if off == prev:
        # Nothing new was consumed (e.g. only a partial trailing record);
        # leave pending/fingerprint state untouched.
        return pairs, corrupt, None

    state["offsets"][key] = off
    if last_asst is not None:
        state["pending"][key] = {
            "assistant": last_asst,
            "timestamp": last_dt,
            "start": last_start,
            "end": last_end,
            "sig": content_hash(last_asst),
        }
    else:
        state["pending"].pop(key, None)
    update_fingerprints(path, key, state, off)
    return pairs, corrupt, None


def discover_sessions(source: Path, since_ts: float | None) -> list[str]:
    files = []
    for f in sorted(glob(str(source / "*" / "*.jsonl"))):
        if not is_safe_input_file(f, source):
            continue
        if since_ts and os.path.getmtime(f) < since_ts:
            continue
        files.append(f)
    return files


def prepare_dirs(out_dir: Path, state_file: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "archive").mkdir(exist_ok=True)
    state_file.parent.mkdir(parents=True, exist_ok=True)


def backlog_path_for(state_file: Path) -> Path:
    """Durable spill file for candidates that exceed --max-proposals."""
    return state_file.with_name(state_file.name + ".backlog.json")


def load_backlog(path: Path) -> list[tuple[float, str, str, str, str]]:
    """Load the durable proposal backlog; fail closed on any invalid shape."""
    if not path.exists():
        return []
    try:
        with open(path, encoding="utf-8") as fp:
            data = json.load(fp)
    except (OSError, json.JSONDecodeError) as exc:
        raise StateError(
            f"proposal backlog {path} is invalid ({exc}); failing closed"
        )
    if not isinstance(data, dict) or not isinstance(data.get("entries", []), list):
        raise StateError(
            f"proposal backlog {path} must contain an object with an entries list"
        )
    entries: list[tuple[float, str, str, str, str]] = []
    for i, item in enumerate(data.get("entries", [])):
        if not isinstance(item, dict):
            raise StateError(f"proposal backlog {path} entries[{i}] must be an object")
        conf = item.get("confidence")
        if isinstance(conf, bool) or not isinstance(conf, (int, float)):
            raise StateError(
                f"proposal backlog {path} entries[{i}].confidence must be a number"
            )
        fields: list[str] = []
        for field in ("hash", "assistant", "reply", "project_dt"):
            value = item.get(field)
            if not isinstance(value, str):
                raise StateError(
                    f"proposal backlog {path} entries[{i}].{field} must be a string"
                )
            fields.append(value)
        entries.append((float(conf), fields[0], fields[1], fields[2], fields[3]))
    return entries


def process_pairs(
    state: dict,
    pairs: list,
    args: argparse.Namespace,
    out_dir: Path,
    existing_descriptions: list[str],
    backlog_file: Path,
) -> int:
    """Classify pairs and write proposals. Candidates past --max-proposals are
    spilled complete into a bounded durable backlog and emitted exactly once on
    a later invocation. If the post-emission spill would exceed the backlog
    bound, fail before publishing any proposal or advancing state. Returns the
    number of proposals written."""
    backlog = load_backlog(backlog_file)
    seen_hashes = set(state["seen_hashes"])
    new_candidates: list[tuple[float, str, str, str, str]] = []
    approved_median = args.approved_median
    if pairs:
        if approved_median <= 0:
            approved_lens = [
                len(r)
                for _a, r, _p, _t in pairs
                if (first_word(r) in APPROVAL_WORDS)
                or (first_word(r) == "sounds" and SOUNDS_APPROVAL_RE.match(r))
            ]
            if approved_lens:
                approved_lens.sort()
                approved_median = float(approved_lens[len(approved_lens) // 2])
            else:
                all_lens = sorted(len(r) for _a, r, _p, _t in pairs)
                approved_median = float(all_lens[len(all_lens) // 2]) / 2 if all_lens else 50.0

        for asst, reply, project, dt_iso in pairs:
            cls, conf = classify(reply, approved_median)
            if cls not in ("explicit_pushback", "implicit_pushback"):
                continue
            if conf < args.min_confidence:
                continue
            if not reply.strip():
                continue
            if covered_by_existing(reply, existing_descriptions):
                continue
            h = content_hash(reply)
            if h in seen_hashes:
                continue
            new_candidates.append((conf, h, asst, reply, project + "|" + dt_iso))

        new_candidates.sort(key=lambda x: -x[0])
        unique: dict[str, tuple[float, str, str, str, str]] = {}
        for cand in new_candidates:
            if cand[1] not in unique:
                unique[cand[1]] = cand
        new_candidates = sorted(unique.values(), key=lambda x: -x[0])
    elif approved_median <= 0:
        approved_median = 50.0

    # Drain the durable backlog first, then freshly qualified candidates.
    pool: list[tuple[float, str, str, str, str]] = []
    pool_hashes = set(seen_hashes)
    for cand in backlog + new_candidates:
        if cand[1] in pool_hashes:
            continue
        pool_hashes.add(cand[1])
        pool.append(cand)

    emission = pool[: args.max_proposals]
    spill = pool[args.max_proposals :]
    if len(spill) > MAX_BACKLOG_ENTRIES:
        raise StateError(
            f"proposal backlog bound exceeded: {len(spill)} deferred candidates "
            f"would exceed the bound of {MAX_BACKLOG_ENTRIES}; no proposals were "
            "published and offsets were not advanced"
        )

    if not pairs and not emission:
        print("No new (assistant, user) pairs since last run.")
        return 0

    if pairs:
        print(f"Scanned {len(pairs)} new pair(s).")
        print(f"Approved-reply median (threshold anchor): {approved_median:.0f} chars.")
        print(f"Existing rule descriptions known: {len(existing_descriptions)}.")
        print(
            f"Candidate proposals after filters: {len(pool)} "
            f"({len(emission)} emitting, {len(spill)} deferred)."
        )

    written = 0
    for conf, h, asst, reply, project_dt in emission:
        project, dt_iso = (project_dt.split("|", 1) + [""])[:2]
        name, body = proposal_body(
            reply, asst, project, dt_iso or datetime.now(timezone.utc).isoformat()
        )
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

    state["seen_hashes"] = list(seen_hashes)[-10000:]
    if not args.dry_run:
        entries = [
            {
                "confidence": conf,
                "hash": h,
                "assistant": asst,
                "reply": reply,
                "project_dt": project_dt,
            }
            for conf, h, asst, reply, project_dt in spill
        ]
        if entries or backlog:
            atomic_write_json(backlog_file, {"version": 1, "entries": entries})
    if spill:
        print(
            f"Deferred {len(spill)} candidate(s) to the durable backlog "
            f"(bound {MAX_BACKLOG_ENTRIES})."
        )
    print(f"\nWrote {written} new proposal(s) to {out_dir}")
    print("Run `/digital-twin:propose-rules` to review them.")
    return written


def run_hook_mode(args: argparse.Namespace, state_file: Path, out_dir: Path) -> int:
    """PostToolUse hook mode. Reads the hook payload from stdin. Fails closed on
    any malformed payload or state; never falls back to manual discovery."""
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError) as exc:
        print(f"ERROR: hook payload is not valid JSON ({exc}).", file=sys.stderr)
        return 2
    if not isinstance(payload, dict):
        print("ERROR: hook payload must be a JSON object.", file=sys.stderr)
        return 2
    event = payload.get("hook_event_name")
    if event != HOOK_EVENT_NAME:
        print(
            f"ERROR: hook payload has missing or invalid hook_event_name "
            f"(expected {HOOK_EVENT_NAME!r}, got {event!r}).",
            file=sys.stderr,
        )
        return 2
    tp = payload.get("transcript_path")
    if not isinstance(tp, str) or not tp.strip():
        print("ERROR: hook payload is missing a nonempty transcript_path.", file=sys.stderr)
        return 2
    key = canonical_path(tp)
    source_root = canonical_path(args.source)
    if not tp.endswith(".jsonl"):
        print(
            f"ERROR: transcript_path must reference a .jsonl transcript (got {tp!r}).",
            file=sys.stderr,
        )
        return 2
    if not os.path.isfile(key):
        print(
            f"ERROR: transcript_path is not a regular file: {key}",
            file=sys.stderr,
        )
        return 2
    try:
        contained = os.path.commonpath([key, source_root]) == source_root
    except ValueError:
        contained = False
    if not contained:
        print(
            f"ERROR: transcript_path {key} is not contained by the canonical "
            f"source root {source_root} (symlink escapes and out-of-root "
            "paths are rejected).",
            file=sys.stderr,
        )
        return 2

    prepare_dirs(out_dir, state_file)
    try:
        with state_lock(state_file):
            state = load_state(state_file, reset=args.reset_state)
            pairs, corrupt, note = scan_file(key, key, state)
            if note:
                print(f"NOTE: {note}", file=sys.stderr)
            if corrupt:
                print(
                    f"WARN: skipped {corrupt} corrupt JSONL line(s) during scan.",
                    file=sys.stderr,
                )
            existing_descriptions = load_existing_descriptions(Path(key).parent.parent)
            process_pairs(
                state, pairs, args, out_dir, existing_descriptions,
                backlog_path_for(state_file),
            )
            if not args.dry_run:
                atomic_write_json(state_file, state)
    except StateError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 3
    return 0


def run_initialize_mode(args: argparse.Namespace, state_file: Path, out_dir: Path) -> int:
    """Baseline missing offsets for existing session files at each file's last
    newline-terminated record. No classification, no proposals."""
    source = Path(args.source).expanduser()
    if not source.exists():
        print(f"ERROR: source not found: {source}", file=sys.stderr)
        return 2
    prepare_dirs(out_dir, state_file)
    since_ts: float | None = None
    if args.since:
        try:
            since_ts = datetime.fromisoformat(args.since).timestamp()
        except ValueError:
            print(f"ERROR: bad --since date: {args.since}", file=sys.stderr)
            return 2
    files = discover_sessions(source, since_ts)
    try:
        with state_lock(state_file):
            state = load_state(state_file, reset=args.reset_state)
            baselined = 0
            for f in files:
                key = canonical_path(f)
                if key in state["offsets"]:
                    continue  # preserve valid existing canonical offsets
                boundary = last_complete_newline_offset(f)
                state["offsets"][key] = boundary
                update_fingerprints(f, key, state, boundary)
                baselined += 1
            if not args.dry_run:
                atomic_write_json(state_file, state)
    except StateError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 3
    print(
        f"Initialized offsets for {baselined} session file(s); "
        f"{len(files) - baselined} already had valid canonical offsets."
    )
    print("No history was classified and no proposals were created.")
    return 0


def run_manual_mode(args: argparse.Namespace, state_file: Path, out_dir: Path) -> int:
    source = Path(args.source).expanduser()
    if not source.exists():
        print(f"ERROR: source not found: {source}", file=sys.stderr)
        return 2
    prepare_dirs(out_dir, state_file)
    since_ts: float | None = None
    if args.since:
        try:
            since_ts = datetime.fromisoformat(args.since).timestamp()
        except ValueError:
            print(f"ERROR: bad --since date: {args.since}", file=sys.stderr)
            return 2
    existing_descriptions = load_existing_descriptions(source)
    try:
        with state_lock(state_file):
            state = load_state(state_file, reset=args.reset_state)
            all_pairs: list[tuple[str, str, str, str]] = []
            corrupt = 0
            for f in discover_sessions(source, since_ts):
                pairs, c, note = scan_file(f, canonical_path(f), state)
                all_pairs.extend(pairs)
                corrupt += c
                if note:
                    print(f"NOTE: {note}", file=sys.stderr)
            if corrupt:
                print(
                    f"WARN: skipped {corrupt} corrupt JSONL line(s) during scan.",
                    file=sys.stderr,
                )
            process_pairs(
                state, all_pairs, args, out_dir, existing_descriptions,
                backlog_path_for(state_file),
            )
            if not args.dry_run:
                atomic_write_json(state_file, state)
    except StateError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 3
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="pushback-detector.py", description=__doc__)
    ap.add_argument(
        "--source",
        default=os.path.expanduser("~/.claude/projects"),
        help="Projects root containing session .jsonl files (default: %(default)s).",
    )
    ap.add_argument(
        "--out-dir",
        default=os.path.expanduser("~/.claude/digital-twin/proposed-rules"),
        help="Queue directory for candidate proposals (default: %(default)s).",
    )
    ap.add_argument(
        "--state-file",
        default=os.path.expanduser("~/.claude/digital-twin/.state.json"),
        help="~/.claude/digital-twin/.state.json is the default incremental state file.",
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
    ap.add_argument(
        "--hook-stdin",
        action="store_true",
        help=(
            "Run as a Claude Code PostToolUse hook: read the hook payload JSON "
            "from stdin and process only its transcript_path incrementally. "
            "There is no fallback to manual discovery."
        ),
    )
    ap.add_argument(
        "--initialize-offsets",
        action="store_true",
        help=(
            "Baseline missing per-file offsets for existing session files to "
            "each file's last newline-terminated record, without classifying "
            "history or creating proposals."
        ),
    )
    args = ap.parse_args(argv)

    if args.hook_stdin and args.initialize_offsets:
        print(
            "ERROR: --hook-stdin and --initialize-offsets are mutually exclusive.",
            file=sys.stderr,
        )
        return 2

    out_dir = Path(args.out_dir).expanduser()
    state_file = Path(canonical_path(args.state_file))

    if args.hook_stdin:
        return run_hook_mode(args, state_file, out_dir)
    if args.initialize_offsets:
        return run_initialize_mode(args, state_file, out_dir)
    return run_manual_mode(args, state_file, out_dir)


if __name__ == "__main__":
    raise SystemExit(main())
