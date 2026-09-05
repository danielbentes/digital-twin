"""
Focused tests for the digital-twin hook installer (skills/digital-twin/scripts/install-hook.py).

Every test that installs passes an explicit temporary --state-file. The
detector's default state location is verified separately in
test_hook_public_interface.py without ever writing to it.
"""
from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
from pathlib import Path

import pytest

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = PLUGIN_ROOT / "skills" / "digital-twin" / "scripts"
INSTALLER = SCRIPTS / "install-hook.py"
DETECTOR = SCRIPTS / "pushback-detector.py"


def run_installer(args: list[str], stdin_text: str | None = "y\n"):
    return subprocess.run(
        [sys.executable, str(INSTALLER), *args],
        input=stdin_text,
        capture_output=True,
        text=True,
        cwd=str(PLUGIN_ROOT),
    )


# Install and uninstall are invoked through SEPARATE helpers so that no
# irrelevant install-only flag can leak into an uninstall invocation.
def run_install(settings: Path, source: Path, state: Path, out_dir: Path, stdin_text: str = "y\n"):
    return run_installer(
        [
            "install",
            "--settings",
            str(settings),
            "--source",
            str(source),
            "--state-file",
            str(state),
            "--out-dir",
            str(out_dir),
        ],
        stdin_text=stdin_text,
    )


def run_uninstall(settings: Path, stdin_text: str = "y\n"):
    return run_installer(["uninstall", "--settings", str(settings)], stdin_text=stdin_text)


def installed_entry(settings_path: Path) -> dict:
    """Return the single marker-owned hook entry the installer manages."""
    data = json.loads(settings_path.read_text(encoding="utf-8"))
    entries = [
        e
        for e in data["hooks"]["PostToolUse"]
        if isinstance(e.get("digital_twin_hook"), dict)
        and e["digital_twin_hook"].get("kind") == "digital-twin/posttooluse-hook"
    ]
    assert len(entries) == 1
    return entries[0]


def recursive_strings(node: object) -> list[str]:
    out: list[str] = []
    if isinstance(node, str):
        out.append(node)
    elif isinstance(node, dict):
        for k, v in node.items():
            out.append(str(k))
            out.extend(recursive_strings(v))
    elif isinstance(node, list):
        for v in node:
            out.extend(recursive_strings(v))
    return out


def write_json(path: Path, obj: dict) -> None:
    path.write_text(json.dumps(obj, indent=2) + "\n", encoding="utf-8")


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


SAMPLE_SETTINGS = {
    "model": "claude-opus-4-6",
    "some_future_field": {"nested": [1, 2, 3]},
    "hooks": {
        "Stop": [{"matcher": "*", "hooks": [{"type": "command", "command": "echo stop"}]}],
        "PostToolUse": [
            {"matcher": "Bash", "hooks": [{"type": "command", "command": "echo user-hook"}]}
        ],
    },
}


# ---------------------------------------------------------------------------
# Confirmation
# ---------------------------------------------------------------------------


def test_prompt_discloses_visible_y_n_choice_for_both_actions(tmp_path: Path):
    settings = tmp_path / "settings.json"
    write_json(settings, dict(SAMPLE_SETTINGS))
    out = run_install(settings, tmp_path, tmp_path / "state.json", tmp_path / "out", "n\n")
    assert "[y/n]" in out.stdout
    assert "install" in out.stdout
    out = run_uninstall(settings, "n\n")
    assert "[y/n]" in out.stdout
    assert "uninstall" in out.stdout


def test_decline_eof_and_unrecognized_do_not_mutate_settings_or_state(tmp_path: Path):
    settings = tmp_path / "settings.json"
    write_json(settings, dict(SAMPLE_SETTINGS))
    original = settings.read_bytes()
    state = tmp_path / "state.json"
    for stdin_text in ("n\n", "", "maybe\n", "N\n"):
        rc = run_install(settings, tmp_path, state, tmp_path / "out", stdin_text)
        assert rc.returncode != 0
        assert settings.read_bytes() == original
        assert not state.exists()
    # Uninstall declines as well.
    assert run_install(settings, tmp_path, state, tmp_path / "out", "y\n").returncode == 0
    after_install = settings.read_bytes()
    for stdin_text in ("n\n", "", "nope\n"):
        rc = run_uninstall(settings, stdin_text)
        assert rc.returncode != 0
        assert settings.read_bytes() == after_install


def test_disclosed_affirmative_forms_accepted_case_insensitively(tmp_path: Path):
    settings = tmp_path / "settings.json"
    write_json(settings, dict(SAMPLE_SETTINGS))
    state = tmp_path / "state.json"
    # The visible prompt is [y/n], so the implementation must accept y and yes.
    for token in ("y\n", "YES\n", "  yes  \n"):
        settings.write_text(json.dumps(SAMPLE_SETTINGS, indent=2) + "\n", encoding="utf-8")
        rc = run_install(settings, tmp_path, state, tmp_path / "out", token)
        assert rc.returncode == 0, rc.stderr
        assert installed_entry(settings)


# ---------------------------------------------------------------------------
# Settings spellings, canonical disclosure, idempotence
# ---------------------------------------------------------------------------


def test_uninstall_accepts_disclosed_affirmatives_case_insensitively(tmp_path: Path):
    settings = tmp_path / "settings.json"
    state = tmp_path / "state.json"
    for token in ("YES\n", "  Y  \n"):
        settings.write_text(json.dumps(SAMPLE_SETTINGS, indent=2) + "\n", encoding="utf-8")
        assert run_install(settings, tmp_path, state, tmp_path / "out", "y\n").returncode == 0
        rc = run_uninstall(settings, token)
        assert rc.returncode == 0, rc.stderr
        assert json.loads(settings.read_text()) == json.loads(json.dumps(SAMPLE_SETTINGS))


def test_both_settings_and_settings_file_spellings(tmp_path: Path):
    state = tmp_path / "state.json"
    for flag in ("--settings", "--settings-file"):
        settings = tmp_path / f"settings-{flag.strip('-')}.json"
        write_json(settings, dict(SAMPLE_SETTINGS))
        args = ["install", flag, str(settings), "--source", str(tmp_path),
                "--state-file", str(state), "--out-dir", str(tmp_path / "out")]
        assert run_installer(args, "y\n").returncode == 0
        assert installed_entry(settings)
        assert run_installer(["uninstall", flag, str(settings)], "y\n").returncode == 0
        assert json.loads(settings.read_text()) == json.loads(json.dumps(SAMPLE_SETTINGS))


def test_canonicalized_target_disclosed_in_prompt(tmp_path: Path):
    real_dir = tmp_path / "real"
    real_dir.mkdir()
    alias = tmp_path / "alias"
    alias.symlink_to(real_dir)
    settings = alias / "settings.json"
    write_json(settings, dict(SAMPLE_SETTINGS))
    canonical = os.path.realpath(settings)
    out = run_install(settings, tmp_path, tmp_path / "state.json", tmp_path / "out", "n\n")
    assert canonical in out.stdout
    out = run_uninstall(settings, "n\n")
    assert canonical in out.stdout


def test_repeated_install_is_byte_idempotent(tmp_path: Path):
    settings = tmp_path / "settings.json"
    write_json(settings, dict(SAMPLE_SETTINGS))
    state = tmp_path / "state.json"
    assert run_install(settings, tmp_path, state, tmp_path / "out", "y\n").returncode == 0
    first = settings.read_bytes()
    rc = run_install(settings, tmp_path, state, tmp_path / "out", "y\n")
    assert rc.returncode == 0
    assert "already installed" in rc.stdout
    assert settings.read_bytes() == first


# ---------------------------------------------------------------------------
# Malformed settings: fail closed, preserve bytes, clear diagnostic
# ---------------------------------------------------------------------------


def test_malformed_settings_json_fails_with_clear_diagnostic_and_preserves_bytes(tmp_path: Path):
    settings = tmp_path / "settings.json"
    settings.write_text('{"hooks": {oops', encoding="utf-8")
    original = settings.read_bytes()
    state = tmp_path / "state.json"
    for runner in (
        lambda: run_install(settings, tmp_path, state, tmp_path / "out", "y\n"),
        lambda: run_uninstall(settings, "y\n"),
    ):
        rc = runner()
        assert rc.returncode != 0
        combined = rc.stdout + rc.stderr
        assert any(w in combined for w in ("invalid", "malformed", "JSON"))
        assert "unreadable" != combined.strip()
        assert settings.read_bytes() == original


@pytest.mark.parametrize(
    "bad",
    [
        {"hooks": {"PostToolUse": "not-a-list"}},
        {"hooks": {"PostToolUse": [{"hooks": [{"type": "command", "command": 5}]}]}},
        {"hooks": {"PostToolUse": [{"hooks": [{"type": "command"}]}]}},
        {"hooks": {"PostToolUse": [{"hooks": [{"type": 7, "command": "x"}]}]}},
        {"hooks": {"PostToolUse": [{"hooks": "not-a-list"}]}},
        {"hooks": "not-an-object"},
    ],
)
def test_nested_malformed_settings_fail_closed(tmp_path: Path, bad: dict):
    settings = tmp_path / "settings.json"
    write_json(settings, bad)
    original = settings.read_bytes()
    state = tmp_path / "state.json"
    rc = run_install(settings, tmp_path, state, tmp_path / "out", "y\n")
    assert rc.returncode != 0
    assert "malformed" in (rc.stdout + rc.stderr) or "invalid" in (rc.stdout + rc.stderr)
    assert settings.read_bytes() == original
    rc = run_uninstall(settings, "y\n")
    assert rc.returncode != 0
    assert settings.read_bytes() == original


# ---------------------------------------------------------------------------
# Installed shape: single detector reference, command-free marker metadata
# ---------------------------------------------------------------------------


def test_exactly_one_detector_reference_and_command_free_marker(tmp_path: Path):
    settings = tmp_path / "settings.json"
    write_json(settings, dict(SAMPLE_SETTINGS))
    state = tmp_path / "state.json"
    assert run_install(settings, tmp_path, state, tmp_path / "out", "y\n").returncode == 0
    data = json.loads(settings.read_text(encoding="utf-8"))
    refs = [s for s in recursive_strings(data) if "pushback-detector.py" in s]
    assert len(refs) == 1
    entry = data["hooks"]["PostToolUse"][-1]
    assert entry["hooks"][0]["command"] == refs[0]
    marker = entry["digital_twin_hook"]
    marker_text = json.dumps(marker)
    assert "pushback-detector" not in marker_text
    assert "command" not in marker_text
    assert marker["kind"] == "digital-twin/posttooluse-hook"
    assert marker["version"] == 1


def test_exact_managed_command_construction(tmp_path: Path):
    settings = tmp_path / "settings.json"
    write_json(settings, dict(SAMPLE_SETTINGS))
    source = tmp_path / "projects"
    source.mkdir()
    state = tmp_path / "state.json"
    out_dir = tmp_path / "out"
    assert run_install(settings, source, state, out_dir, "y\n").returncode == 0
    command = installed_entry(settings)["hooks"][0]["command"]
    # No shell masking or redirection.
    for forbidden in (">", "2>&1", "||", "|", "&"):
        assert forbidden not in command
    argv = shlex.split(command)
    assert argv[0] == sys.executable
    assert argv[1] == os.path.realpath(DETECTOR)
    assert "--hook-stdin" in argv
    assert argv[argv.index("--source") + 1] == os.path.realpath(source)
    assert argv[argv.index("--state-file") + 1] == os.path.realpath(state)
    assert argv[argv.index("--out-dir") + 1] == os.path.realpath(out_dir)


def test_install_only_flags_absent_from_uninstall_help(tmp_path: Path):
    install_help = run_installer(["install", "--help"], stdin_text=None)
    uninstall_help = run_installer(["uninstall", "--help"], stdin_text=None)
    assert install_help.returncode == 0 and uninstall_help.returncode == 0
    for flag in ("--source", "--state-file", "--out-dir"):
        assert flag in install_help.stdout
        assert flag not in uninstall_help.stdout
    for flag in ("--settings", "--settings-file"):
        assert flag in install_help.stdout
        assert flag in uninstall_help.stdout


def test_stable_default_state_location_advertised():
    help_text = run_installer(["install", "--help"], stdin_text=None).stdout
    assert "~/.claude/digital-twin/.state.json" in help_text


# ---------------------------------------------------------------------------
# Structural round trips
# ---------------------------------------------------------------------------


def test_round_trip_from_populated_settings(tmp_path: Path):
    settings = tmp_path / "settings.json"
    write_json(settings, dict(SAMPLE_SETTINGS))
    original = json.loads(settings.read_text())
    state = tmp_path / "state.json"
    assert run_install(settings, tmp_path, state, tmp_path / "out", "y\n").returncode == 0
    installed = json.loads(settings.read_text())
    assert installed["model"] == original["model"]
    assert installed["some_future_field"] == original["some_future_field"]
    assert installed["hooks"]["Stop"] == original["hooks"]["Stop"]
    assert installed["hooks"]["PostToolUse"][:-1] == original["hooks"]["PostToolUse"]
    assert run_uninstall(settings, "y\n").returncode == 0
    assert json.loads(settings.read_text()) == original


def test_round_trip_from_absent_settings_file(tmp_path: Path):
    settings = tmp_path / "settings.json"
    state = tmp_path / "state.json"
    assert run_install(settings, tmp_path, state, tmp_path / "out", "y\n").returncode == 0
    assert installed_entry(settings)
    assert run_uninstall(settings, "y\n").returncode == 0
    assert json.loads(settings.read_text()) == {}


def test_round_trip_preserves_user_authored_empty_post_tool_use(tmp_path: Path):
    original: dict[str, object] = {"hooks": {"PostToolUse": []}}
    settings = tmp_path / "settings.json"
    write_json(settings, original)
    state = tmp_path / "state.json"
    assert run_install(settings, tmp_path, state, tmp_path / "out", "y\n").returncode == 0
    assert installed_entry(settings)
    assert run_uninstall(settings, "y\n").returncode == 0
    assert json.loads(settings.read_text()) == original


def test_round_trip_preserves_user_authored_empty_hooks_container(tmp_path: Path):
    original: dict[str, object] = {"hooks": {}}
    settings = tmp_path / "settings.json"
    write_json(settings, original)
    state = tmp_path / "state.json"
    assert run_install(settings, tmp_path, state, tmp_path / "out", "y\n").returncode == 0
    assert installed_entry(settings)
    assert run_uninstall(settings, "y\n").returncode == 0
    assert json.loads(settings.read_text()) == original


def test_uninstall_when_not_installed_is_a_noop(tmp_path: Path):
    settings = tmp_path / "settings.json"
    write_json(settings, dict(SAMPLE_SETTINGS))
    original = settings.read_bytes()
    rc = run_uninstall(settings, "y\n")
    assert rc.returncode == 0
    assert settings.read_bytes() == original


# ---------------------------------------------------------------------------
# Install-time initialization integration
# ---------------------------------------------------------------------------


def _run_hook_command(command: str, payload: dict):
    return subprocess.run(
        shlex.split(command),
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        cwd=str(PLUGIN_ROOT),
    )


def test_confirmed_install_baselines_history_then_hook_emits_only_new_pair(tmp_path: Path):
    # A lexical alias for the projects root: initialization must key state by
    # the canonical identity so a later canonical hook payload cannot replay.
    real_projects = tmp_path / "projects-real"
    real_projects.mkdir()
    alias_projects = tmp_path / "projects-alias"
    alias_projects.symlink_to(real_projects)
    project = real_projects / "-demo"
    project.mkdir()
    transcript = project / "session.jsonl"
    make_transcript(
        transcript,
        [
            ("Historical assistant draft about quarterly planning.", "stop — that's the wrong approach"),
            ("Historical assistant draft two.", "thanks"),
        ],
    )

    state = tmp_path / "deep" / "state.json"  # parent does not exist yet
    assert not state.exists()
    out_dir = tmp_path / "proposals"
    settings = tmp_path / "settings.json"
    write_json(settings, dict(SAMPLE_SETTINGS))

    # Run ONLY the confirmed installer. No direct state initialization anywhere.
    rc = run_install(settings, alias_projects, state, out_dir, "y\n")
    assert rc.returncode == 0, rc.stderr

    assert state.exists()
    st = json.loads(state.read_text(encoding="utf-8"))
    canonical = os.path.realpath(transcript)
    data = transcript.read_bytes()
    final_boundary = data.rindex(b"\n") + 1
    assert st["offsets"][canonical] == final_boundary
    # No historical replay produced proposals.
    assert list(out_dir.glob("*.md")) == []

    # Append one new assistant-user pair and fire the installed hook command.
    with open(transcript, "a", encoding="utf-8") as fp:
        fp.write(
            json.dumps(
                {
                    "type": "assistant",
                    "timestamp": "2026-05-02T10:00:00Z",
                    "message": {"content": "Fresh assistant proposal with a new plan."},
                }
            )
            + "\n"
        )
        fp.write(
            json.dumps(
                {
                    "type": "user",
                    "timestamp": "2026-05-02T10:00:30Z",
                    "message": {"content": "actually, that is not what I asked for"},
                }
            )
            + "\n"
        )

    payload = {"hook_event_name": "PostToolUse", "transcript_path": canonical}
    hook = _run_hook_command(installed_entry(settings)["hooks"][0]["command"], payload)
    assert hook.returncode == 0, hook.stderr

    proposals = [p for p in out_dir.glob("*.md") if p.name != "archive"]
    assert len(proposals) == 1
    body = proposals[0].read_text(encoding="utf-8")
    assert "actually, that is not what I asked for" in body
    assert "Historical assistant draft" not in body
    assert "quarterly planning" not in body

    # Second identical event is a no-op (incremental, no duplicate).
    hook2 = _run_hook_command(installed_entry(settings)["hooks"][0]["command"], payload)
    assert hook2.returncode == 0, hook2.stderr
    proposals2 = [p for p in out_dir.glob("*.md") if p.name != "archive"]
    assert len(proposals2) == 1


def test_install_propagates_detector_initialization_failure_and_preserves_settings(tmp_path: Path):
    settings = tmp_path / "settings.json"
    write_json(settings, dict(SAMPLE_SETTINGS))
    original = settings.read_bytes()
    state = tmp_path / "state.json"
    missing_source = tmp_path / "does-not-exist"
    rc = run_install(settings, missing_source, state, tmp_path / "out", "y\n")
    assert rc.returncode != 0
    assert settings.read_bytes() == original
    assert not state.exists()
