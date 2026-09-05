"""
Focused incremental-behavior tests for pushback-detector.py: canonical
identity, durable pending-assistant pairing across invocations, malformed
complete records, backlog capping/draining, concurrency, atomic publication,
the registered /digital-twin:propose-rules surface, manual availability, and
event-local no-op latency.
"""
from __future__ import annotations

import importlib.util
import inspect
import io
import json
import os
import statistics
import subprocess
import sys
import time
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = PLUGIN_ROOT / "skills" / "digital-twin" / "scripts"
DETECTOR = SCRIPTS / "pushback-detector.py"

_spec = importlib.util.spec_from_file_location("pushback_detector_inc", DETECTOR)
assert _spec is not None and _spec.loader is not None
pushback_detector = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pushback_detector)


def run_detector(args: list[str], stdin_text: str | None = None):
    return subprocess.run(
        [sys.executable, str(DETECTOR), *args],
        input=stdin_text,
        capture_output=True,
        text=True,
        cwd=str(PLUGIN_ROOT),
    )


def hook_args(state: Path, out_dir: Path) -> list[str]:
    return [
        "--hook-stdin",
        "--source", str(state.parent / "projects"),
        "--state-file", str(state),
        "--out-dir", str(out_dir),
    ]


def run_hook(state: Path, out_dir: Path, transcript: Path, extra: list[str] | None = None):
    payload = {"hook_event_name": "PostToolUse", "transcript_path": str(transcript)}
    return run_detector(hook_args(state, out_dir) + (extra or []), stdin_text=json.dumps(payload))


def init_offsets(state: Path, out_dir: Path, source: Path, extra: list[str] | None = None):
    return run_detector(
        ["--initialize-offsets", "--source", str(source),
         "--state-file", str(state), "--out-dir", str(out_dir)] + (extra or [])
    )


def make_transcript(path: Path, pairs: list[tuple[str, str | None]]) -> None:
    ts_i = 0

    def stamp() -> str:
        nonlocal ts_i
        ts_i += 1
        return f"2026-05-01T09:{ts_i % 60:02d}:{ts_i // 60:02d}Z"

    lines = []
    for asst, user in pairs:
        lines.append(json.dumps(
            {"type": "assistant", "timestamp": stamp(), "message": {"content": asst}}))
        if user is not None:
            lines.append(json.dumps(
                {"type": "user", "timestamp": stamp(), "message": {"content": user}}))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def append_line(path: Path, obj: dict) -> None:
    with open(path, "a", encoding="utf-8") as fp:
        fp.write(json.dumps(obj) + "\n")


def asst(text: str, t: str) -> dict:
    return {"type": "assistant", "timestamp": t, "message": {"content": text}}


def user(text: str, t: str) -> dict:
    return {"type": "user", "timestamp": t, "message": {"content": text}}


def proposals_in(out_dir: Path) -> list[Path]:
    return sorted(p for p in out_dir.glob("*.md") if p.is_file())


def corpus(tmp_path: Path) -> tuple[Path, Path]:
    source = tmp_path / "projects"
    proj = source / "-demo"
    proj.mkdir(parents=True)
    return source, proj / "session.jsonl"


# ---------------------------------------------------------------------------
# Initialization: baseline only, canonical key, no replay
# ---------------------------------------------------------------------------


def test_initialize_offsets_baselines_canonical_boundary_without_replay(tmp_path):
    source, transcript = corpus(tmp_path)
    make_transcript(transcript, [("assistant one", "thanks"),
                                 ("assistant two", "stop, that is wrong")])
    with open(transcript, "a", encoding="utf-8") as fp:
        fp.write('{"type":"assistant","message":{"content":"partial tail')
    state = tmp_path / "state.json"
    out_dir = tmp_path / "proposals"
    rc = init_offsets(state, out_dir, source)
    assert rc.returncode == 0, rc.stderr
    canonical = os.path.realpath(transcript)
    st = json.loads(state.read_text())
    expected = transcript.read_bytes().rindex(b"\n") + 1
    assert st["offsets"] == {canonical: expected}
    assert "pending" in st and st["pending"].get(canonical) is None
    assert proposals_in(out_dir) == []
    # No historical pair was classified: a subsequent canonical hook is a no-op.
    rc = run_hook(state, out_dir, Path(canonical))
    assert rc.returncode == 0, rc.stderr
    assert proposals_in(out_dir) == []


def test_alias_init_then_canonical_hook_reuses_offset_and_emits_one_pair(tmp_path):
    source, transcript = corpus(tmp_path)
    alias_source = tmp_path / "alias-projects"
    alias_source.symlink_to(source)
    make_transcript(transcript, [("historical assistant text", "stop, wrong approach")])
    state = tmp_path / "state.json"
    out_dir = tmp_path / "proposals"
    rc = init_offsets(state, out_dir, alias_source)
    assert rc.returncode == 0, rc.stderr
    canonical = os.path.realpath(transcript)
    st = json.loads(state.read_text())
    assert list(st["offsets"]) == [canonical]

    append_line(transcript, asst("Fresh appended plan.", "2026-05-01T10:00:00Z"))
    append_line(transcript, user("hold on, that is not right at all", "2026-05-01T10:00:20Z"))
    rc = run_hook(state, out_dir, Path(canonical))
    assert rc.returncode == 0, rc.stderr
    proposals = proposals_in(out_dir)
    assert len(proposals) == 1
    body = proposals[0].read_text()
    assert "hold on, that is not right at all" in body
    assert "historical assistant text" not in body
    st = json.loads(state.read_text())
    assert st["pending"].get(canonical) is None
    # No duplicate lexical alias keys in any per-file state map.
    assert list(st["offsets"]) == [canonical]
    assert list(st["fingerprints"]) == [canonical]


# ---------------------------------------------------------------------------
# Incremental hook consumption and pending assistant persistence
# ---------------------------------------------------------------------------


def test_two_hook_calls_process_only_appended_records(tmp_path):
    source, transcript = corpus(tmp_path)
    make_transcript(transcript, [("old assistant", "thanks")])
    state = tmp_path / "state.json"
    out_dir = tmp_path / "proposals"
    assert init_offsets(state, out_dir, source).returncode == 0
    canonical = os.path.realpath(transcript)
    base_offset = json.loads(state.read_text())["offsets"][canonical]

    append_line(transcript, asst("Assistant plan A.", "2026-05-01T10:00:00Z"))
    assert run_hook(state, out_dir, Path(canonical)).returncode == 0
    st = json.loads(state.read_text())
    assert st["offsets"][canonical] > base_offset
    assert st["pending"][canonical]["assistant"] == "Assistant plan A."
    assert proposals_in(out_dir) == []

    append_line(transcript, user("wait, that is wrong", "2026-05-01T10:00:30Z"))
    assert run_hook(state, out_dir, Path(canonical)).returncode == 0
    # Refresh the snapshot: the second invocation emitted the pair and
    # advanced offsets, so subsequent no-op comparisons must use this state.
    st = json.loads(state.read_text())
    proposals = proposals_in(out_dir)
    assert len(proposals) == 1
    assert "Assistant plan A." in proposals[0].read_text()

    # Third call: nothing new; nothing changes.
    before = state.read_bytes()
    rc = run_hook(state, out_dir, Path(canonical))
    assert rc.returncode == 0, rc.stderr
    assert json.loads(state.read_text())["offsets"][canonical] == st["offsets"][canonical]
    assert len(proposals_in(out_dir)) == 1
    assert state.read_bytes() == before


def test_incomplete_tail_waits_for_newline(tmp_path):
    source, transcript = corpus(tmp_path)
    make_transcript(transcript, [("old assistant", "thanks")])
    state = tmp_path / "state.json"
    out_dir = tmp_path / "proposals"
    assert init_offsets(state, out_dir, source).returncode == 0
    canonical = os.path.realpath(transcript)
    base_offset = json.loads(state.read_text())["offsets"][canonical]

    with open(transcript, "a", encoding="utf-8") as fp:
        fp.write(json.dumps(asst("Partial assistant record", "2026-05-01T10:01:00Z")))
    rc = run_hook(state, out_dir, Path(canonical))
    assert rc.returncode == 0, rc.stderr
    st = json.loads(state.read_text())
    assert st["offsets"][canonical] == base_offset
    assert canonical not in st["pending"]

    with open(transcript, "a", encoding="utf-8") as fp:
        fp.write("\n")
    rc = run_hook(state, out_dir, Path(canonical))
    assert rc.returncode == 0, rc.stderr
    st = json.loads(state.read_text())
    assert st["pending"][canonical]["assistant"] == "Partial assistant record"
    assert st["offsets"][canonical] > base_offset


def test_complete_malformed_record_fails_before_advancing(tmp_path):
    source, transcript = corpus(tmp_path)
    make_transcript(transcript, [("old assistant", "thanks")])
    state = tmp_path / "state.json"
    out_dir = tmp_path / "proposals"
    assert init_offsets(state, out_dir, source).returncode == 0
    canonical = os.path.realpath(transcript)
    base_offset = json.loads(state.read_text())["offsets"][canonical]

    append_line(transcript, asst("Good assistant turn.", "2026-05-01T10:02:00Z"))
    with open(transcript, "a", encoding="utf-8") as fp:
        fp.write("{not valid json at all\n")
    rc = run_hook(state, out_dir, Path(canonical))
    assert rc.returncode != 0
    st = json.loads(state.read_text())
    assert st["offsets"][canonical] == base_offset
    assert proposals_in(out_dir) == []
    # The qualifying pair before the malformed record was not published either.
    assert json.loads(state.read_text())["pending"].get(canonical) is None


def test_hook_ignores_unrelated_malformed_transcript_after_baseline(tmp_path):
    source, transcript = corpus(tmp_path)
    make_transcript(transcript, [("old assistant", "thanks")])
    state = tmp_path / "state.json"
    out_dir = tmp_path / "proposals"
    assert init_offsets(state, out_dir, source).returncode == 0

    unrelated = source / "-demo" / "unrelated.jsonl"
    unrelated.write_text("garbage line\n{also bad\n", encoding="utf-8")

    append_line(transcript, asst("Assistant plan B.", "2026-05-01T10:03:00Z"))
    append_line(transcript, user("no, stop, revert this", "2026-05-01T10:03:30Z"))
    rc = run_hook(state, out_dir, Path(os.path.realpath(transcript)))
    assert rc.returncode == 0, rc.stderr
    st = json.loads(state.read_text())
    assert os.path.realpath(unrelated) not in st["offsets"]
    assert len(proposals_in(out_dir)) == 1


# ---------------------------------------------------------------------------
# Hook payload validation: malformed and escaped input preserve state
# ---------------------------------------------------------------------------


def test_malformed_and_escaped_hook_input_preserve_state_and_proposals(tmp_path):
    source, transcript = corpus(tmp_path)
    make_transcript(transcript, [("assistant", "actually that is wrong")])
    state = tmp_path / "state.json"
    out_dir = tmp_path / "proposals"
    assert run_hook(state, out_dir, transcript).returncode == 0
    assert len(proposals_in(out_dir)) == 1
    state_before = state.read_bytes()
    canonical = os.path.realpath(transcript)

    # A symlink inside the source root escaping to a file outside the root.
    outside_dir = tmp_path / "outside"
    outside_dir.mkdir()
    outside = outside_dir / "escaped.jsonl"
    make_transcript(outside, [("assistant", "outside pushback")])
    link = source / "-demo" / "link.jsonl"
    link.symlink_to(outside)

    bad_payloads = [
        "{not json",
        "{}{}",
        "42",
        json.dumps({"hook_event_name": "PreToolUse", "transcript_path": canonical}),
        json.dumps({"hook_event_name": "PostToolUse"}),
        json.dumps({"hook_event_name": "PostToolUse", "transcript_path": ""}),
        # Not a .jsonl transcript.
        json.dumps({"hook_event_name": "PostToolUse", "transcript_path": str(state)}),
        # A directory inside the root.
        json.dumps({"hook_event_name": "PostToolUse", "transcript_path": str(source)}),
        # A symlink escaping the canonical source root.
        json.dumps({"hook_event_name": "PostToolUse", "transcript_path": str(link)}),
        # An out-of-root regular file.
        json.dumps({"hook_event_name": "PostToolUse", "transcript_path": str(outside)}),
        # A nonexistent in-root path.
        json.dumps({"hook_event_name": "PostToolUse",
                    "transcript_path": str(source / "-demo" / "missing.jsonl")}),
    ]
    for payload in bad_payloads:
        rc = run_detector(hook_args(state, out_dir), stdin_text=payload)
        assert rc.returncode != 0, payload
        assert state.read_bytes() == state_before, payload
        assert len(proposals_in(out_dir)) == 1, payload


# ---------------------------------------------------------------------------
# Replacement handling (equal, smaller, larger) never cross-pairs
# ---------------------------------------------------------------------------


def _replacement_case(tmp_path, mode: str):
    source, transcript = corpus(tmp_path)
    make_transcript(transcript, [("old assistant", "thanks")])
    state = tmp_path / "state.json"
    out_dir = tmp_path / "proposals"
    assert init_offsets(state, out_dir, source).returncode == 0
    canonical = os.path.realpath(transcript)

    original = json.dumps(asst("STALE assistant plan to replace.", "2026-05-01T12:00:00Z")) + "\n"
    with open(transcript, "a", encoding="utf-8") as fp:
        fp.write(original)
    assert run_hook(state, out_dir, Path(canonical)).returncode == 0
    assert json.loads(state.read_text())["pending"][canonical]["assistant"].startswith("STALE")

    if mode == "equal":
        replacement = json.dumps(asst("Rplc assistant plan replaced!", "2026-05-01T12:00:00Z")) + "\n"
        pad = len(original) - len(replacement)
        assert pad >= 0
        replacement = json.dumps(
            asst("Rplc assistant plan replaced!" + "x" * pad, "2026-05-01T12:00:00Z")) + "\n"
        assert len(replacement) == len(original)
    elif mode == "smaller":
        replacement = json.dumps(asst("small", "2026-05-01T12:00:00Z")) + "\n"
    else:
        replacement = json.dumps(
            asst("much larger replacement assistant record " * 3, "2026-05-01T12:00:00Z")) + "\n"

    data = transcript.read_bytes()
    assert data.endswith(original.encode())
    transcript.write_bytes(data[: -len(original)] + replacement.encode())

    # A user record appended after the replacement must never cross-pair with
    # the stale pending assistant, and the replacement itself must not be
    # classified as history.
    append_line(transcript, user("ok, proceed", "2026-05-01T12:00:30Z"))
    rc = run_hook(state, out_dir, Path(canonical))
    assert rc.returncode == 0, rc.stderr
    st = json.loads(state.read_text())
    assert canonical not in st["pending"]
    for p in proposals_in(out_dir):
        body = p.read_text()
        assert "STALE assistant plan" not in body
        assert "Rplc" not in body
        assert "much larger replacement" not in body
    assert "small" not in "\n".join(p.read_text() for p in proposals_in(out_dir))

    # A later normal append must NOT look like another replacement.
    append_line(transcript, asst("Fresh post-replacement plan.", "2026-05-01T13:00:00Z"))
    rc = run_hook(state, out_dir, Path(canonical))
    assert rc.returncode == 0, rc.stderr
    st = json.loads(state.read_text())
    assert st["pending"][canonical]["assistant"] == "Fresh post-replacement plan."
    append_line(transcript, user("actually, revert that", "2026-05-01T13:00:30Z"))
    rc = run_hook(state, out_dir, Path(canonical))
    assert rc.returncode == 0, rc.stderr
    proposals = proposals_in(out_dir)
    assert len(proposals) == 1
    assert "actually, revert that" in proposals[0].read_text()
    assert "Fresh post-replacement plan." in proposals[0].read_text()


def test_replacement_equal_size_no_cross_pair(tmp_path):
    _replacement_case(tmp_path, "equal")


def test_replacement_smaller_no_cross_pair(tmp_path):
    _replacement_case(tmp_path, "smaller")


def test_replacement_larger_no_cross_pair(tmp_path):
    _replacement_case(tmp_path, "larger")


# ---------------------------------------------------------------------------
# Backlog: capping, draining exactly once, bound, overflow
# ---------------------------------------------------------------------------


def _burst_args(state: Path, out_dir: Path) -> list[str]:
    return hook_args(state, out_dir) + ["--max-proposals", "2"]


def test_capped_candidates_deferred_and_drained_exactly_once(tmp_path):
    source, transcript = corpus(tmp_path)
    make_transcript(transcript, [("old assistant", "thanks")])
    state = tmp_path / "state.json"
    out_dir = tmp_path / "proposals"
    assert init_offsets(state, out_dir, source).returncode == 0
    canonical = os.path.realpath(transcript)

    # A qualifying burst of 5 pushbacks, capped at 2 per invocation.
    for i in range(5):
        append_line(transcript, asst(f"Burst assistant turn number {i}.", f"2026-05-01T14:{i:02d}:00Z"))
        append_line(transcript, user(f"no, stop, this burst {i} is wrong", f"2026-05-01T14:{i:02d}:30Z"))
    rc = run_detector(_burst_args(state, out_dir), stdin_text=json.dumps(
        {"hook_event_name": "PostToolUse", "transcript_path": canonical}))
    assert rc.returncode == 0, rc.stderr
    assert len(proposals_in(out_dir)) == 2
    backlog = json.loads(Path(str(state) + ".backlog.json").read_text())
    assert len(backlog["entries"]) == 3

    # Drain 2, then 1; nothing repeats and nothing is lost.
    rc = run_detector(_burst_args(state, out_dir), stdin_text=json.dumps(
        {"hook_event_name": "PostToolUse", "transcript_path": canonical}))
    assert rc.returncode == 0, rc.stderr
    assert len(proposals_in(out_dir)) == 4
    rc = run_detector(_burst_args(state, out_dir), stdin_text=json.dumps(
        {"hook_event_name": "PostToolUse", "transcript_path": canonical}))
    assert rc.returncode == 0, rc.stderr
    all_proposals = proposals_in(out_dir)
    assert len(all_proposals) == 5
    bodies = [p.read_text() for p in all_proposals]
    for i in range(5):
        assert sum(f"burst {i} is wrong" in b for b in bodies) == 1
    assert not Path(str(state) + ".backlog.json").exists() or \
        json.loads(Path(str(state) + ".backlog.json").read_text())["entries"] == []


def test_backlog_at_bound_can_drain_and_overflow_fails_closed(tmp_path):
    bound = pushback_detector.MAX_BACKLOG_ENTRIES
    source, transcript = corpus(tmp_path)
    state = tmp_path / "state.json"
    out_dir = tmp_path / "proposals"
    make_transcript(transcript, [("seed assistant", "thanks")])
    assert init_offsets(state, out_dir, source).returncode == 0
    canonical = os.path.realpath(transcript)
    backlog_path = Path(str(state) + ".backlog.json")
    with_cap1 = hook_args(state, out_dir) + ["--max-proposals", "1"]

    def burst(tag: str, count: int, hour: int) -> None:
        for i in range(count):
            append_line(transcript, asst(
                f"{tag} assistant {i}.",
                f"2026-05-02T{hour:02d}:{i % 60:02d}:00Z"))
            append_line(transcript, user(
                f"no, this {tag} {i} is wrong",
                f"2026-05-02T{hour:02d}:{i % 60:02d}:30Z"))

    def backlog_size() -> int:
        if not backlog_path.exists():
            return 0
        return len(json.loads(backlog_path.read_text())["entries"])

    # 200 candidates, capped at 1: 1 emitted, 199 spilled.
    burst("bound", bound, 12)
    rc = run_detector(with_cap1, stdin_text=json.dumps(
        {"hook_event_name": "PostToolUse", "transcript_path": canonical}))
    assert rc.returncode == 0, rc.stderr
    assert backlog_size() == bound - 1

    # Two more candidates land the backlog exactly at the bound (199+2-1).
    burst("top-up", 2, 13)
    rc = run_detector(with_cap1, stdin_text=json.dumps(
        {"hook_event_name": "PostToolUse", "transcript_path": canonical}))
    assert rc.returncode == 0, rc.stderr
    assert backlog_size() == bound

    # A backlog exactly at the bound must remain drainable: one more candidate
    # emits one and keeps the spill at the bound.
    burst("drain", 1, 14)
    rc = run_detector(with_cap1, stdin_text=json.dumps(
        {"hook_event_name": "PostToolUse", "transcript_path": canonical}))
    assert rc.returncode == 0, rc.stderr
    assert backlog_size() == bound

    # Post-emission overflow: two new candidates with only one emitted leave
    # bound + 1 deferred; must fail WITHOUT publishing proposals or advancing
    # offsets, and the preexisting backlog must be intact.
    offset_before = json.loads(state.read_text())["offsets"][canonical]
    backlog_before = backlog_path.read_bytes()
    burst("trigger", 2, 15)
    rc = run_detector(with_cap1, stdin_text=json.dumps(
        {"hook_event_name": "PostToolUse", "transcript_path": canonical}))
    assert rc.returncode != 0
    st = json.loads(state.read_text())
    assert st["offsets"][canonical] == offset_before
    assert backlog_path.read_bytes() == backlog_before
    assert backlog_size() == bound

    # A retry with a larger cap drains everything exactly once; the preexisting
    # backlog plus the burst candidates are all emitted, none duplicated.
    rc = run_detector(hook_args(state, out_dir) + ["--max-proposals", str(bound + 2)],
                      stdin_text=json.dumps(
                          {"hook_event_name": "PostToolUse",
                           "transcript_path": canonical}))
    assert rc.returncode == 0, rc.stderr
    assert backlog_size() == 0
    # Count PROPOSALS, not raw substring occurrences: each proposal body
    # legitimately embeds the reply text three times (frontmatter description,
    # correction sentence, and evidence line). A duplicated emission would
    # still be caught because it produces a second proposal file.
    all_bodies = [p.read_text() for p in proposals_in(out_dir)]

    def files_with(text: str) -> int:
        return sum(text in b for b in all_bodies)

    for i in range(bound):
        assert files_with(f"this bound {i} is wrong") == 1
    assert files_with("this top-up 0 is wrong") == 1
    assert files_with("this top-up 1 is wrong") == 1
    assert files_with("this drain 0 is wrong") == 1
    assert files_with("this trigger 0 is wrong") == 1
    assert files_with("this trigger 1 is wrong") == 1


# ---------------------------------------------------------------------------
# Concurrency, atomic publication, output surface, idempotence, manual mode
# ---------------------------------------------------------------------------


def test_overlapping_hook_processes_preserve_both_updates(tmp_path):
    source, transcript_a = corpus(tmp_path)
    transcript_b = source / "-demo" / "session-b.jsonl"
    make_transcript(transcript_a, [("old", "thanks")])
    make_transcript(transcript_b, [("old", "thanks")])
    state = tmp_path / "state.json"
    out_dir = tmp_path / "proposals"
    assert init_offsets(state, out_dir, source).returncode == 0
    for t, plan, push in ((transcript_a, "Concurrent plan A.", "no, plan A is wrong"),
                          (transcript_b, "Concurrent plan B.", "no, plan B is wrong")):
        append_line(t, asst(plan, "2026-05-03T10:00:00Z"))
        append_line(t, user(push, "2026-05-03T10:00:30Z"))

    payload_a = json.dumps({"hook_event_name": "PostToolUse",
                            "transcript_path": str(os.path.realpath(transcript_a))})
    payload_b = json.dumps({"hook_event_name": "PostToolUse",
                            "transcript_path": str(os.path.realpath(transcript_b))})
    procs = [
        subprocess.Popen([sys.executable, str(DETECTOR), *hook_args(state, out_dir)],
                         stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE, text=True)
        for _ in range(2)
    ]
    outs = []
    for proc, payload in zip(procs, (payload_a, payload_b)):
        out, err = proc.communicate(payload, timeout=60)
        outs.append((proc.returncode, out, err))
    for rc, _out, err in outs:
        assert rc == 0, err
    st = json.loads(state.read_text())
    canonical_a = os.path.realpath(transcript_a)
    canonical_b = os.path.realpath(transcript_b)
    assert canonical_a in st["offsets"] and canonical_b in st["offsets"]
    bodies = "\n".join(p.read_text() for p in proposals_in(out_dir))
    assert "plan A is wrong" in bodies
    assert "plan B is wrong" in bodies


def test_every_state_publication_uses_atomic_replacement(tmp_path, monkeypatch):
    source, transcript = corpus(tmp_path)
    make_transcript(transcript, [("assistant", "actually that is wrong")])
    state = tmp_path / "state.json"
    out_dir = tmp_path / "proposals"
    canonical = os.path.realpath(transcript)

    # Use the production state-file naming convention (dot-prefixed), which
    # the atomic-replacement assertions below identify by suffix.
    state = tmp_path / ".state.json"

    replacements: list[str] = []
    real_replace = os.replace  # noqa: B008
    monkeypatch.setattr(os, "replace",
                        lambda a, b, *a2, **k: (replacements.append(str(b)),
                                                real_replace(a, b, *a2, **k))[1])

    payload = json.dumps({"hook_event_name": "PostToolUse", "transcript_path": canonical})
    stdin_guard = sys.stdin
    # Initialization publication.
    monkeypatch.setattr(sys, "stdin", io.StringIO(""))
    pushback_detector.main(["--initialize-offsets", "--source", str(source),
                            "--state-file", str(state), "--out-dir", str(out_dir)])
    # Proposal-producing hook publication.
    monkeypatch.setattr(sys, "stdin", io.StringIO(payload))
    pushback_detector.main(hook_args(state, out_dir))
    # No-op checkpoint publication.
    monkeypatch.setattr(sys, "stdin", io.StringIO(payload))
    pushback_detector.main(hook_args(state, out_dir))
    # Manual publication.
    monkeypatch.setattr(sys, "stdin", stdin_guard)
    pushback_detector.main(["--source", str(source), "--state-file", str(state),
                            "--out-dir", str(out_dir)])
    monkeypatch.undo()

    assert any(str(p).endswith(".state.json") for p in map(Path, replacements))
    state_publications = [p for p in replacements if p.endswith(".state.json")]
    assert len(state_publications) >= 3
    assert not list(tmp_path.glob("*.tmp.*"))

    # Source-level guard: atomic_write_json must fsync a sibling temp file and
    # os.replace it; it must never open() the state target directly for writing.
    src = inspect.getsource(pushback_detector.atomic_write_json)
    assert "os.replace(tmp, path)" in src
    assert "os.fsync" in src
    assert 'open(tmp, "w"' in src
    assert 'open(path, "w"' not in src


def test_proposal_output_names_registered_command(tmp_path):
    source, transcript = corpus(tmp_path)
    make_transcript(transcript, [("assistant", "actually that is wrong")])
    state = tmp_path / "state.json"
    out_dir = tmp_path / "proposals"
    rc = run_hook(state, out_dir, transcript)
    assert rc.returncode == 0, rc.stderr
    assert "/digital-twin:propose-rules" in rc.stdout
    assert "/digital-twin propose-rules" not in rc.stdout
    assert len(proposals_in(out_dir)) == 1


def test_noop_hook_is_idempotent(tmp_path):
    source, transcript = corpus(tmp_path)
    make_transcript(transcript, [("assistant", "actually that is wrong")])
    state = tmp_path / "state.json"
    out_dir = tmp_path / "proposals"
    canonical = os.path.realpath(transcript)
    assert run_hook(state, out_dir, Path(canonical)).returncode == 0
    first_state = state.read_bytes()
    n_proposals = len(proposals_in(out_dir))
    rc = run_hook(state, out_dir, Path(canonical))
    assert rc.returncode == 0, rc.stderr
    assert state.read_bytes() == first_state
    assert len(proposals_in(out_dir)) == n_proposals


def test_manual_mode_remains_available(tmp_path):
    source, transcript = corpus(tmp_path)
    make_transcript(transcript, [("assistant", "actually that is wrong")])
    state = tmp_path / "state.json"
    out_dir = tmp_path / "proposals"
    rc = run_detector(["--source", str(source), "--state-file", str(state),
                       "--out-dir", str(out_dir)])
    assert rc.returncode == 0, rc.stderr
    assert len(proposals_in(out_dir)) == 1
    assert "/digital-twin:propose-rules" in rc.stdout
    st = json.loads(state.read_text())
    assert st["offsets"][os.path.realpath(transcript)] == transcript.stat().st_size


# ---------------------------------------------------------------------------
# Event-local no-op latency after a realistic 1,000-pair append
# ---------------------------------------------------------------------------


def test_noop_hook_latency_after_1000_pair_append(tmp_path):
    source, transcript = corpus(tmp_path)
    make_transcript(transcript, [("seed assistant", "thanks")])
    state = tmp_path / "state.json"
    out_dir = tmp_path / "proposals"
    assert init_offsets(state, out_dir, source).returncode == 0
    canonical = os.path.realpath(transcript)

    with open(transcript, "a", encoding="utf-8") as fp:
        for i in range(1000):
            fp.write(json.dumps(asst(
                f"Realistic assistant turn {i} with a moderate amount of detail.",
                f"2026-05-04T{(i // 3600) % 24:02d}:{(i // 60) % 60:02d}:{i % 60:02d}Z")) + "\n")
            fp.write(json.dumps(user(
                f"thanks, that realistic reply {i} looks good",
                f"2026-05-04T{(i // 3600) % 24:02d}:{(i // 60) % 60:02d}:{i % 60:02d}Z")) + "\n")
    # Consume the appended history once so subsequent hooks are no-ops.
    rc = run_hook(state, out_dir, Path(canonical))
    assert rc.returncode == 0, rc.stderr

    durations = []
    payload = json.dumps({"hook_event_name": "PostToolUse", "transcript_path": canonical})
    for _ in range(5):
        start = time.perf_counter()
        rc = run_detector(hook_args(state, out_dir), stdin_text=payload)
        durations.append(time.perf_counter() - start)
        assert rc.returncode == 0, rc.stderr
    assert statistics.median(durations) < 0.400, durations
    assert max(durations) < 1.000, durations
