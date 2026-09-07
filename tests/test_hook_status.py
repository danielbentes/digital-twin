"""
Focused subprocess tests for the read-only `status` subcommand of
skills/digital-twin/scripts/install-hook.py.

Every invocation uses an explicit temporary --settings path and closed
stdin: status must never prompt, so any read attempt would see EOF, and any
side effect would be visible in the temporary directory.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
INSTALLER = PLUGIN_ROOT / "skills" / "digital-twin" / "scripts" / "install-hook.py"

MANAGED_ENTRY = {
    "matcher": "*",
    "hooks": [{"type": "command", "command": "python3 /should/never/run/detector.py --hook-stdin"}],
    "digital_twin_hook": {
        "kind": "digital-twin/posttooluse-hook",
        "version": 1,
        "installed_at": "2026-05-01T09:00:00+00:00",
        "source": "/tmp/source",
        "state_file": "/tmp/state.json",
        "out_dir": "/tmp/out",
        "created_containers": [],
    },
}


def run_status(settings: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(INSTALLER), "status", "--settings", str(settings)],
        input="",
        capture_output=True,
        text=True,
        cwd=str(PLUGIN_ROOT),
    )


def write_json(path: Path, obj: object) -> None:
    path.write_text(json.dumps(obj, indent=2) + "\n", encoding="utf-8")


def parse_single_object(completed: subprocess.CompletedProcess[str]) -> dict:
    """Assert exactly one JSON object on stdout and no extra keys."""
    lines = [line for line in completed.stdout.splitlines() if line.strip()]
    assert len(lines) == 1
    obj = json.loads(lines[0])
    assert set(obj) == {"version", "installed", "managedHookCount"}
    assert obj["version"] == 1
    assert isinstance(obj["installed"], bool)
    assert isinstance(obj["managedHookCount"], int) and not isinstance(obj["managedHookCount"], bool)
    return obj


# ---------------------------------------------------------------------------
# Installed, absent, missing parent, duplicates
# ---------------------------------------------------------------------------


def test_status_installed_reports_true_and_counts_managed_entries(tmp_path: Path):
    settings = tmp_path / "settings.json"
    write_json(
        settings,
        {
            "hooks": {
                "PostToolUse": [
                    {"matcher": "Bash", "hooks": [{"type": "command", "command": "echo user-hook"}]},
                    MANAGED_ENTRY,
                ]
            }
        },
    )
    completed = run_status(settings)
    assert completed.returncode == 0, completed.stderr
    obj = parse_single_object(completed)
    assert obj["installed"] is True
    assert obj["managedHookCount"] == 1


def test_status_without_managed_marker_reports_not_installed(tmp_path: Path):
    settings = tmp_path / "settings.json"
    write_json(
        settings,
        {"hooks": {"PostToolUse": [{"matcher": "*", "hooks": [{"type": "command", "command": "echo x"}]}]}},
    )
    completed = run_status(settings)
    assert completed.returncode == 0, completed.stderr
    obj = parse_single_object(completed)
    assert obj == {"version": 1, "installed": False, "managedHookCount": 0}


def test_status_counts_duplicate_registrations_without_collapsing(tmp_path: Path):
    settings = tmp_path / "settings.json"
    write_json(
        settings,
        {"hooks": {"PostToolUse": [MANAGED_ENTRY, dict(MANAGED_ENTRY), MANAGED_ENTRY]}},
    )
    completed = run_status(settings)
    assert completed.returncode == 0, completed.stderr
    obj = parse_single_object(completed)
    assert obj["installed"] is True
    assert obj["managedHookCount"] == 3


# ---------------------------------------------------------------------------
# Missing settings create nothing; both spellings and the default work
# ---------------------------------------------------------------------------


def test_status_missing_settings_reports_zero_and_creates_nothing(tmp_path: Path):
    settings = tmp_path / "settings.json"
    assert not settings.exists()
    completed = run_status(settings)
    assert completed.returncode == 0, completed.stderr
    assert parse_single_object(completed) == {"version": 1, "installed": False, "managedHookCount": 0}
    assert not settings.exists()
    assert list(tmp_path.iterdir()) == []


def test_status_missing_parent_directory_reports_zero_and_creates_nothing(tmp_path: Path):
    settings = tmp_path / "missing-parent" / "nested" / "settings.json"
    completed = run_status(settings)
    assert completed.returncode == 0, completed.stderr
    assert parse_single_object(completed) == {"version": 1, "installed": False, "managedHookCount": 0}
    assert not (tmp_path / "missing-parent").exists()


def test_status_accepts_settings_file_spelling(tmp_path: Path):
    settings = tmp_path / "settings.json"
    write_json(settings, {"hooks": {"PostToolUse": [MANAGED_ENTRY]}})
    completed = subprocess.run(
        [sys.executable, str(INSTALLER), "status", "--settings-file", str(settings)],
        input="",
        capture_output=True,
        text=True,
        cwd=str(PLUGIN_ROOT),
    )
    assert completed.returncode == 0, completed.stderr
    assert parse_single_object(completed)["managedHookCount"] == 1


def test_status_declares_default_settings_location_in_help():
    completed = subprocess.run(
        [sys.executable, str(INSTALLER), "status", "--help"],
        input="",
        capture_output=True,
        text=True,
        cwd=str(PLUGIN_ROOT),
    )
    assert completed.returncode == 0, completed.stderr
    help_text = completed.stdout
    assert "settings.json" in help_text
    assert "default" in help_text
    for flag in ("--source", "--state-file", "--out-dir"):
        assert flag not in completed.stdout


# ---------------------------------------------------------------------------
# Malformed / unreadable / invalid nested types fail closed on stderr
# ---------------------------------------------------------------------------


def test_status_malformed_json_fails_nonzero_on_stderr_without_success_json(tmp_path: Path):
    settings = tmp_path / "settings.json"
    settings.write_text('{"hooks": {oops', encoding="utf-8")
    completed = run_status(settings)
    assert completed.returncode != 0
    assert completed.stdout.strip() == ""
    assert "ERROR" in completed.stderr
    assert any(w in completed.stderr for w in ("invalid", "malformed", "JSON"))


def test_status_non_object_settings_fail_nonzero_on_stderr(tmp_path: Path):
    settings = tmp_path / "settings.json"
    write_json(settings, ["not", "an", "object"])
    completed = run_status(settings)
    assert completed.returncode != 0
    assert completed.stdout.strip() == ""
    assert completed.stderr.strip() != ""


def test_status_invalid_nested_types_fail_nonzero_on_stderr(tmp_path: Path):
    bad_cases = [
        {"hooks": "not-an-object"},
        {"hooks": {"PostToolUse": "not-a-list"}},
        {"hooks": {"PostToolUse": [{"hooks": "not-a-list"}]}},
        {"hooks": {"PostToolUse": [{"hooks": [{"type": 7, "command": "x"}]}]}},
        {"hooks": {"PostToolUse": [{"hooks": [{"type": "command", "command": 5}]}]}},
        {"hooks": {"PostToolUse": [{"hooks": [{"type": "command"}]}]}},
    ]
    for bad in bad_cases:
        settings = tmp_path / "settings.json"
        write_json(settings, bad)
        completed = run_status(settings)
        assert completed.returncode != 0, bad
        assert completed.stdout.strip() == "", bad
        assert completed.stderr.strip() != "", bad


def test_status_unreadable_settings_fail_nonzero_on_stderr(tmp_path: Path):
    settings = tmp_path / "settings.json"
    write_json(settings, {"hooks": {"PostToolUse": [MANAGED_ENTRY]}})
    os.chmod(settings, 0)  # deny every permission for the current user
    completed = run_status(settings)
    if completed.returncode == 0:
        assert parse_single_object(completed)["managedHookCount"] == 1
    else:
        assert completed.stdout.strip() == ""
        assert "unreadable" in completed.stderr


# ---------------------------------------------------------------------------
# Nonmutation and never-executes evidence
# ---------------------------------------------------------------------------


def test_status_never_mutates_settings_or_state_and_creates_nothing(tmp_path: Path):
    settings = tmp_path / "settings.json"
    write_json(settings, {"hooks": {"PostToolUse": [MANAGED_ENTRY]}})
    original = settings.read_bytes()
    state = tmp_path / "state.json"
    assert run_status(settings).returncode == 0
    assert settings.read_bytes() == original
    assert not state.exists()
    assert [p.name for p in tmp_path.iterdir()] == ["settings.json"]


def test_status_does_not_execute_detector_or_hook_commands(tmp_path: Path):
    sentinel = tmp_path / "executed.sentinel"
    entry = json.loads(json.dumps(MANAGED_ENTRY))
    # If anything executed this command, the sentinel file would be created.
    entry["hooks"][0]["command"] = (
        f'"{sys.executable}" -c "open({str(sentinel)!r}, \'w\').close()"'
    )
    settings = tmp_path / "settings.json"
    write_json(settings, {"hooks": {"PostToolUse": [entry]}})
    completed = run_status(settings)
    assert completed.returncode == 0, completed.stderr
    assert parse_single_object(completed)["installed"] is True
    assert not sentinel.exists(), "status must never execute hook commands"
    assert "detector.py" not in completed.stdout


def test_status_json_excludes_settings_values_and_commands(tmp_path: Path):
    secret = "claude-sk-ant-super-secret-value"
    entry = json.loads(json.dumps(MANAGED_ENTRY))
    entry["hooks"][0]["command"] = secret
    settings = tmp_path / "settings.json"
    write_json(settings, {"api_key": secret, "hooks": {"PostToolUse": [entry]}})
    completed = run_status(settings)
    assert completed.returncode == 0, completed.stderr
    assert secret not in completed.stdout
    assert "/should/never/run" not in completed.stdout


def test_status_never_prompts_even_with_closed_stdin(tmp_path: Path):
    settings = tmp_path / "settings.json"
    write_json(settings, {"hooks": {"PostToolUse": [MANAGED_ENTRY]}})
    completed = run_status(settings)  # input="" -> stdin is closed/empty
    assert completed.returncode == 0, completed.stderr
    assert "[y/n]" not in completed.stdout
    assert "[y/n]" not in completed.stderr
