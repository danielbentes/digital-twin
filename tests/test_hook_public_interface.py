"""
Focused tests for the pushback-detector's public hook/initialization surface:
--hook-stdin, --initialize-offsets, fail-closed state handling, canonical
transcript identity, bounded rewrite detection, and the documented default
state location.
"""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = PLUGIN_ROOT / "skills" / "digital-twin" / "scripts"
DETECTOR = SCRIPTS / "pushback-detector.py"

_spec = importlib.util.spec_from_file_location("pushback_detector", DETECTOR)
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


def run_hook(state: Path, transcript: Path, extra_args: list[str] | None = None):
    payload = {"hook_event_name": "PostToolUse", "transcript_path": str(transcript)}
    return run_detector(
        ["--hook-stdin", "--source", str(transcript.parent.parent),
         "--state-file", str(state), "--out-dir", str(state.parent / "proposals")]
        + (extra_args or []),
        stdin_text=json.dumps(payload),
    )


def make_transcript(path: Path, pairs: list[tuple[str, str | None]]) -> None:
    ts_i = 0

    def stamp() -> str:
        nonlocal ts_i
        ts_i += 1
        return f"2026-05-01T09:{ts_i:02d}:00Z"

    lines = []
    for asst, user in pairs:
        lines.append(
            json.dumps(
                {"type": "assistant", "timestamp": stamp(), "message": {"content": asst}}
            )
        )
        if user is not None:
            lines.append(
                json.dumps({"type": "user", "timestamp": stamp(), "message": {"content": user}})
            )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def proposals_in(out_dir: Path) -> list[Path]:
    return [p for p in out_dir.glob("*.md") if p.name != "archive"]


def corpus(tmp_path: Path) -> tuple[Path, Path]:
    source = tmp_path / "projects"
    proj = source / "-demo"
    proj.mkdir(parents=True)
    return source, proj / "session.jsonl"


# ---------------------------------------------------------------------------
# Public --initialize-offsets mode
# ---------------------------------------------------------------------------


def test_initialize_offsets_baselines_last_complete_boundary_with_partial_tail(tmp_path: Path):
    source, transcript = corpus(tmp_path)
    make_transcript(transcript, [("assistant one", "thanks")])
    with open(transcript, "a", encoding="utf-8") as fp:
        fp.write('{"type":"assistant","message":{"content":"partial tail rec')  # no newline

    state = tmp_path / "state.json"
    rc = run_detector(
        ["--initialize-offsets", "--source", str(source), "--state-file", str(state),
         "--out-dir", str(tmp_path / "proposals")]
    )
    assert rc.returncode == 0, rc.stderr
    data = transcript.read_bytes()
    expected = data.rindex(b"\n") + 1
    st = json.loads(state.read_text())
    assert st["offsets"][os.path.realpath(transcript)] == expected
    assert proposals_in(tmp_path / "proposals") == []


def test_initialize_offsets_preserves_valid_existing_offsets(tmp_path: Path):
    source, transcript = corpus(tmp_path)
    make_transcript(transcript, [("assistant one", "thanks")])
    state = tmp_path / "state.json"
    keep = 5
    state.write_text(json.dumps({"offsets": {os.path.realpath(transcript): keep}}), encoding="utf-8")
    rc = run_detector(
        ["--initialize-offsets", "--source", str(source), "--state-file", str(state),
         "--out-dir", str(tmp_path / "proposals")]
    )
    assert rc.returncode == 0, rc.stderr
    st = json.loads(state.read_text())
    assert st["offsets"][os.path.realpath(transcript)] == keep


# ---------------------------------------------------------------------------
# --hook-stdin payload validation: fail closed, no mutation, no replay
# ---------------------------------------------------------------------------


def test_hook_stdin_rejects_malformed_payloads(tmp_path: Path):
    source, transcript = corpus(tmp_path)
    make_transcript(transcript, [("assistant", "stop — wrong")])
    state = tmp_path / "state.json"
    out_dir = tmp_path / "proposals"
    bad_payloads = [
        "{}",
        json.dumps({"transcript_path": str(transcript)}),
        json.dumps({"hook_event_name": "PostToolUse"}),
        json.dumps({"hook_event_name": "PreToolUse", "transcript_path": str(transcript)}),
        json.dumps({"hook_event_name": "PostToolUse", "transcript_path": ""}),
        "not json at all",
    ]
    for payload in bad_payloads:
        rc = run_detector(
            ["--hook-stdin", "--state-file", str(state), "--out-dir", str(out_dir)],
            stdin_text=payload,
        )
        assert rc.returncode != 0, payload
        assert not state.exists(), payload
        assert proposals_in(out_dir) == [], payload


def test_hook_stdin_has_no_fallback_to_manual_discovery(tmp_path: Path):
    source, transcript = corpus(tmp_path)
    make_transcript(transcript, [("assistant", "stop — wrong")])
    # A valid payload but a nonexistent state dir parent is created; the hook
    # must process ONLY the payload transcript, never scan --source.
    other = tmp_path / "projects" / "-other" / "secret.jsonl"
    other.parent.mkdir(parents=True)
    make_transcript(other, [("assistant", "stop — wrong")])
    state = tmp_path / "state.json"
    rc = run_hook(state, transcript)
    assert rc.returncode == 0, rc.stderr
    st = json.loads(state.read_text())
    assert os.path.realpath(other) not in st["offsets"]
    assert os.path.realpath(transcript) in st["offsets"]


# ---------------------------------------------------------------------------
# Fail-closed state handling
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "broken",
    [
        "{not json",
        "[1, 2, 3]",
        json.dumps({"offsets": {"x": "not-an-int"}}),
        json.dumps({"offsets": {"x": -3}}),
        json.dumps({"pending": {"x": {"assistant": 42}}}),
        json.dumps({"fingerprints": {"x": {"leading": {"start": "0", "end": 1, "sha256": "d"}}}}),
        json.dumps({"seen_hashes": [7]}),
    ],
)
def test_hook_and_manual_fail_closed_on_invalid_state(tmp_path: Path, broken: str):
    source, transcript = corpus(tmp_path)
    make_transcript(transcript, [("assistant", "actually — that's wrong")])
    out_dir = tmp_path / "proposals"
    state = tmp_path / "state.json"
    state.write_text(broken, encoding="utf-8")
    original = state.read_bytes()

    rc = run_hook(state, transcript)
    assert rc.returncode != 0
    assert state.read_bytes() == original
    assert proposals_in(out_dir) == []

    rc = run_detector(
        ["--source", str(source), "--state-file", str(state), "--out-dir", str(out_dir)]
    )
    assert rc.returncode != 0
    assert state.read_bytes() == original
    assert proposals_in(out_dir) == []


# ---------------------------------------------------------------------------
# Incremental hook processing, canonical identity, aliasing
# ---------------------------------------------------------------------------


def test_alias_lexical_init_then_canonical_hook_does_not_replay(tmp_path: Path):
    source, transcript = corpus(tmp_path)
    alias_source = tmp_path / "alias-projects"
    alias_source.symlink_to(source)
    make_transcript(transcript, [("historical assistant text", "stop — wrong approach")])
    state = tmp_path / "state.json"
    rc = run_detector(
        ["--initialize-offsets", "--source", str(alias_source), "--state-file", str(state),
         "--out-dir", str(tmp_path / "proposals")]
    )
    assert rc.returncode == 0, rc.stderr
    canonical = os.path.realpath(transcript)
    # Fire the hook using the canonical path; history must not be replayed.
    rc = run_hook(state, Path(canonical))
    assert rc.returncode == 0, rc.stderr
    assert proposals_in(tmp_path / "proposals") == []


def test_hook_processes_pending_assistant_then_user_incrementally(tmp_path: Path):
    source, transcript = corpus(tmp_path)
    make_transcript(transcript, [("old assistant", "thanks")])
    state = tmp_path / "state.json"
    out_dir = tmp_path / "proposals"
    assert run_detector(
        ["--initialize-offsets", "--source", str(source), "--state-file", str(state),
         "--out-dir", str(out_dir)]
    ).returncode == 0
    canonical = os.path.realpath(transcript)

    with open(transcript, "a", encoding="utf-8") as fp:
        fp.write(json.dumps({"type": "assistant", "timestamp": "2026-05-01T10:00:00Z",
                             "message": {"content": "New assistant turn with a plan."}}) + "\n")
    rc = run_hook(state, Path(canonical))
    assert rc.returncode == 0, rc.stderr
    assert proposals_in(out_dir) == []
    st = json.loads(state.read_text())
    pending = st["pending"][canonical]
    assert pending["assistant"] == "New assistant turn with a plan."
    assert pending["sig"]

    with open(transcript, "a", encoding="utf-8") as fp:
        fp.write(json.dumps({"type": "user", "timestamp": "2026-05-01T10:00:30Z",
                             "message": {"content": "wait, that is not what I wanted"}}) + "\n")
    rc = run_hook(state, Path(canonical))
    assert rc.returncode == 0, rc.stderr
    proposals = proposals_in(out_dir)
    assert len(proposals) == 1
    body = proposals[0].read_text()
    assert "wait, that is not what I wanted" in body
    assert "old assistant" not in body


def test_large_transcript_partial_tail_then_completion(tmp_path: Path):
    W = pushback_detector.LEADING_FINGERPRINT_WINDOW
    source, transcript = corpus(tmp_path)
    lines: list[str] = []
    i = 0
    while sum(len(x) + 1 for x in lines) < W:
        i += 1
        lines.append(json.dumps({"type": "user", "timestamp": f"2026-05-01T09:{i:02d}:00Z",
                                 "message": {"content": f"filler message number {i} padding"}}))
        lines.append(json.dumps({"type": "assistant", "timestamp": f"2026-05-01T09:{i:02d}:10Z",
                                 "message": {"content": f"filler assistant reply {i}"}}))
    with open(transcript, "w", encoding="utf-8") as fp:
        fp.write("\n".join(lines) + "\n")
        # Partial trailing assistant record (no newline yet).
        fp.write('{"type":"assistant","timestamp":"2026-05-01T11:00:00Z","message":{"content":"partial')
    state = tmp_path / "state.json"
    out_dir = tmp_path / "proposals"
    assert run_detector(
        ["--initialize-offsets", "--source", str(source), "--state-file", str(state),
         "--out-dir", str(out_dir)]
    ).returncode == 0
    canonical = os.path.realpath(transcript)
    data = transcript.read_bytes()
    boundary = data.rindex(b"\n") + 1
    assert json.loads(state.read_text())["offsets"][canonical] == boundary
    assert len(data) > W

    # Complete the partial record (close content string, message object, and
    # the root object) and add the user reply.
    with open(transcript, "a", encoding="utf-8") as fp:
        fp.write('"}}\n')
        fp.write(json.dumps({"type": "user", "timestamp": "2026-05-01T11:00:10Z",
                             "message": {"content": "hold on, that's not right at all"}}) + "\n")
    rc = run_hook(state, Path(canonical))
    assert rc.returncode == 0, rc.stderr
    proposals = proposals_in(out_dir)
    assert len(proposals) == 1
    assert "hold on, that's not right at all" in proposals[0].read_text()


# ---------------------------------------------------------------------------
# Same-size trailing rewrite detection beyond the leading fingerprint window
# ---------------------------------------------------------------------------


def test_same_size_trailing_rewrite_detected_and_processing_resumes_once(tmp_path: Path):
    W = pushback_detector.LEADING_FINGERPRINT_WINDOW
    source, transcript = corpus(tmp_path)
    # Build a transcript larger than the declared leading-fingerprint window
    # (fixture size derived from W, not a fixed byte count).
    filler: list[str] = []
    i = 0
    while sum(len(x) + 1 for x in filler) < W:
        i += 1
        filler.append(json.dumps({"type": "user", "timestamp": f"2026-05-01T09:{i:02d}:00Z",
                                  "message": {"content": f"filler user message {i} with padding"}}))
        filler.append(json.dumps({"type": "assistant", "timestamp": f"2026-05-01T09:{i:02d}:10Z",
                                  "message": {"content": f"filler assistant reply {i}"}}))
    with open(transcript, "w", encoding="utf-8") as fp:
        fp.write("\n".join(filler) + "\n")
    state = tmp_path / "state.json"
    out_dir = tmp_path / "proposals"
    # Baseline BEFORE the trailing assistant record exists.
    assert run_detector(
        ["--initialize-offsets", "--source", str(source), "--state-file", str(state),
         "--out-dir", str(out_dir)]
    ).returncode == 0

    stale_text = "STALE assistant plan that must never be classified."
    with open(transcript, "a", encoding="utf-8") as fp:
        fp.write(json.dumps({"type": "assistant", "timestamp": "2026-05-01T12:00:00Z",
                             "message": {"content": stale_text}}) + "\n")
    assert transcript.stat().st_size > W
    canonical = os.path.realpath(transcript)

    # Consume the trailing assistant as a durable pending entry.
    assert run_hook(state, Path(canonical)).returncode == 0
    st = json.loads(state.read_text())
    assert st["pending"][canonical]["assistant"] == stale_text

    # Same-size rewrite: preserve the leading window AND total byte size while
    # replacing the complete trailing assistant record.
    data = transcript.read_bytes()
    marker = (json.dumps({"type": "assistant", "timestamp": "2026-05-01T12:00:00Z",
                          "message": {"content": stale_text}}) + "\n").encode()
    start = data.index(marker)
    rewritten_base = "REWROTE trailing assistant record."
    rewritten_text = rewritten_base + "x" * (len(stale_text) - len(rewritten_base))
    new_record = json.dumps({"type": "assistant", "timestamp": "2026-05-01T12:00:00Z",
                             "message": {"content": rewritten_text}}) + "\n"
    assert len(new_record) == len(marker)
    rewritten = data[:start] + new_record.encode()
    assert len(rewritten) == len(data)
    transcript.write_bytes(rewritten)
    # Append one user record that would cross-pair with the stale text.
    with open(transcript, "a", encoding="utf-8") as fp:
        fp.write(json.dumps({"type": "user", "timestamp": "2026-05-01T12:00:30Z",
                             "message": {"content": "ok proceed"}}) + "\n")

    assert run_hook(state, Path(canonical)).returncode == 0
    st = json.loads(state.read_text())
    assert canonical not in st["pending"]  # stale pending discarded
    assert proposals_in(out_dir) == []  # no cross-pair with stale assistant

    # Normal processing resumes exactly once with a fresh complete pair.
    with open(transcript, "a", encoding="utf-8") as fp:
        fp.write(json.dumps({"type": "assistant", "timestamp": "2026-05-01T13:00:00Z",
                             "message": {"content": "Fresh post-rewrite assistant turn."}}) + "\n")
        fp.write(json.dumps({"type": "user", "timestamp": "2026-05-01T13:00:20Z",
                             "message": {"content": "no — stop, revert that change"}}) + "\n")
    assert run_hook(state, Path(canonical)).returncode == 0
    proposals = proposals_in(out_dir)
    assert len(proposals) == 1
    body = proposals[0].read_text()
    assert "no — stop, revert that change" in body
    assert stale_text not in body
    assert rewritten_text not in body
    assert run_hook(state, Path(canonical)).returncode == 0
    assert len(proposals_in(out_dir)) == 1  # still exactly one


# ---------------------------------------------------------------------------
# Output, atomic state, defaults
# ---------------------------------------------------------------------------


def test_manual_output_names_registered_propose_rules_command(tmp_path: Path):
    source, transcript = corpus(tmp_path)
    make_transcript(transcript, [("assistant", "actually that is wrong")])
    state = tmp_path / "state.json"
    rc = run_detector(
        ["--source", str(source), "--state-file", str(state), "--out-dir", str(tmp_path / "proposals")]
    )
    assert rc.returncode == 0, rc.stderr
    assert "/digital-twin:propose-rules" in rc.stdout


def test_state_written_atomically_without_temp_leftovers(tmp_path: Path):
    source, transcript = corpus(tmp_path)
    make_transcript(transcript, [("assistant", "stop — wrong")])
    state = tmp_path / "state.json"
    assert run_hook(state, transcript).returncode == 0
    assert json.loads(state.read_text())
    leftovers = [p for p in state.parent.iterdir() if ".tmp." in p.name]
    assert leftovers == []


def test_default_state_location_is_stable():
    help_text = run_detector(["--help"]).stdout
    assert "~/.claude/digital-twin/.state.json" in help_text


def test_hook_and_initialize_modes_are_mutually_exclusive(tmp_path: Path):
    rc = run_detector(["--hook-stdin", "--initialize-offsets", "--state-file", str(tmp_path / "s.json")],
                      stdin_text="{}")
    assert rc.returncode != 0
