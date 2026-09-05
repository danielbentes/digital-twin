#!/usr/bin/env python3
"""
install-hook.py — explicit, reversible installer for the digital-twin
pushback-detector PostToolUse hook (issue #6).

Subcommands:
    install    Register the detector as a PostToolUse hook in the selected
               settings file. Requires explicit interactive confirmation.
    uninstall  Remove only marker-owned hook entries introduced by this
               installer, pruning only containers it created. Requires
               explicit interactive confirmation.

Settings selection accepts both --settings and --settings-file spellings.
Only `install` exposes --source, --state-file, and --out-dir; uninstall does
not consume them.

Guarantees:
  * No mutation of settings or detector state without an explicit confirmed
    response to a prompt that names the action and discloses the accepted
    affirmative forms ([y/n] -> y/yes, case-insensitive). Declines, EOF, and
    unrecognized responses preserve all bytes.
  * Malformed settings JSON fails nonzero with a clear diagnostic and leaves
    the file byte-identical.
  * Unknown settings fields are preserved (forward compatibility).
  * Installation adds exactly one marker-owned PostToolUse entry and is
    byte-idempotent when repeated.
  * Marker metadata is command-free: it records kind/version, a timestamp,
    the canonical source/state/out-dir provenance needed for a reversible
    uninstall, and which hook containers the installer itself introduced.
  * Exactly one string in the whole installed settings value references
    pushback-detector.py: the executable hook command itself. The command
    invokes the canonical detector with --hook-stdin plus the canonical
    --source, --state-file, and --out-dir. No shell masking or redirection.
  * After confirmation and before publishing settings, the installer runs
    the detector's public --initialize-offsets mode with the same canonical
    values embedded in the managed command. If initialization fails, the
    settings bytes are unchanged and no success is reported.
"""
from __future__ import annotations

import argparse
import builtins
import json
import os
import shlex
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
DETECTOR_SCRIPT = SCRIPT_DIR / "pushback-detector.py"

DEFAULT_SETTINGS = os.path.expanduser("~/.claude/settings.json")
DEFAULT_SOURCE = os.path.expanduser("~/.claude/projects")
DEFAULT_STATE_FILE = os.path.expanduser("~/.claude/digital-twin/.state.json")
DEFAULT_OUT_DIR = os.path.expanduser("~/.claude/digital-twin/proposed-rules")

MARKER_KEY = "digital_twin_hook"
MARKER_KIND = "digital-twin/posttooluse-hook"
MARKER_VERSION = 1


class SettingsError(Exception):
    """Raised when a settings file cannot be safely processed."""


def canonical(path: str) -> str:
    return os.path.realpath(os.path.abspath(os.path.expanduser(str(path))))


def validate_settings(data: object, path: str) -> None:
    """Validate every settings and nested hook container, including the types of
    known inner `type` and `command` fields. Unknown fields are allowed."""

    def fail(why: str) -> SettingsError:
        return SettingsError(
            f"ERROR: settings file {path} is malformed: {why}. No changes were made."
        )

    if not isinstance(data, dict):
        raise fail("top level must be a JSON object")
    if "hooks" not in data:
        return
    hooks = data["hooks"]
    if not isinstance(hooks, dict):
        raise fail("`hooks` must be a JSON object")
    if "PostToolUse" not in hooks:
        return
    entries = hooks["PostToolUse"]
    if not isinstance(entries, list):
        raise fail("`hooks.PostToolUse` must be a JSON array")
    for i, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise fail(f"`hooks.PostToolUse[{i}]` must be a JSON object")
        if "matcher" in entry and not isinstance(entry["matcher"], str):
            raise fail(f"`hooks.PostToolUse[{i}].matcher` must be a string")
        if "hooks" not in entry:
            continue
        inner = entry["hooks"]
        if not isinstance(inner, list):
            raise fail(f"`hooks.PostToolUse[{i}].hooks` must be a JSON array")
        for j, hook in enumerate(inner):
            if not isinstance(hook, dict):
                raise fail(f"`hooks.PostToolUse[{i}].hooks[{j}]` must be a JSON object")
            htype = hook.get("type")
            if not isinstance(htype, str) or not htype.strip():
                raise fail(f"`hooks.PostToolUse[{i}].hooks[{j}].type` must be a nonempty string")
            if htype == "command":
                cmd = hook.get("command")
                if not isinstance(cmd, str) or not cmd.strip():
                    raise fail(
                        f"`hooks.PostToolUse[{i}].hooks[{j}].command` must be a "
                        "nonempty string for a command hook"
                    )


def load_settings(path: str) -> dict:
    try:
        with open(path, encoding="utf-8") as fp:
            text = fp.read()
    except FileNotFoundError:
        raise
    except OSError as exc:
        raise SettingsError(f"ERROR: settings file {path} is unreadable ({exc}).")
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise SettingsError(
            f"ERROR: settings file {path} contains invalid JSON (malformed: "
            f"{exc.msg} at line {exc.lineno}, column {exc.colno}). No changes were made."
        )
    validate_settings(data, path)
    return data


def marker_owned_entries(data: dict) -> list[dict]:
    hooks = data.get("hooks")
    if not isinstance(hooks, dict):
        return []
    entries = hooks.get("PostToolUse")
    if not isinstance(entries, list):
        return []
    owned = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        marker = entry.get(MARKER_KEY)
        if isinstance(marker, dict) and marker.get("kind") == MARKER_KIND:
            owned.append(entry)
    return owned


def is_installed(data: dict) -> bool:
    return bool(marker_owned_entries(data))


def prompt_confirm(action: str, target: str) -> bool:
    """Prompt the user for explicit confirmation. The prompt names the action,
    displays the canonical target, and discloses a visible [y/n] choice. Only
    the disclosed affirmative forms (y/yes, case-insensitive, whitespace
    trimmed) are accepted; everything else, including EOF, declines without
    mutating anything."""
    prompt = (
        f"About to {action} the digital-twin PostToolUse hook in:\n"
        f"  {target}\n"
        f"Confirm {action}? [y/n] "
    )
    try:
        answer = builtins.input(prompt)
    except EOFError:
        print("\nNo response received (EOF). Nothing was changed.")
        return False
    token = answer.strip().lower()
    if token in ("y", "yes"):
        return True
    print(
        f"Response {answer!r} is not a disclosed affirmative (y/yes). "
        "Nothing was changed."
    )
    return False


def build_hook_command(source: str, state_file: str, out_dir: str) -> str:
    return shlex.join(
        [
            sys.executable,
            str(DETECTOR_SCRIPT),
            "--hook-stdin",
            "--source",
            canonical(source),
            "--state-file",
            canonical(state_file),
            "--out-dir",
            canonical(out_dir),
            "--max-proposals",
            "5",
        ]
    )


def run_initialize_offsets(source: str, state_file: str, out_dir: str) -> int:
    """Execute the detector's public --initialize-offsets mode with the same
    canonical values embedded in the managed hook command. stderr/stdout
    propagate to the user untouched."""
    cmd = [
        sys.executable,
        str(DETECTOR_SCRIPT),
        "--initialize-offsets",
        "--source",
        canonical(source),
        "--state-file",
        canonical(state_file),
        "--out-dir",
        canonical(out_dir),
    ]
    completed = subprocess.run(cmd)
    return completed.returncode


def atomic_write_settings(path: str, data: dict) -> None:
    directory = os.path.dirname(path) or "."
    fd, tmp = tempfile.mkstemp(prefix=".settings.", suffix=".tmp", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fp:
            json.dump(data, fp, indent=2)
            fp.write("\n")
            fp.flush()
            os.fsync(fp.fileno())
        os.replace(tmp, path)
        dir_fd = os.open(directory, os.O_RDONLY)
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


def load_settings_or_target(path: str) -> dict:
    if not os.path.exists(path):
        return {}
    return load_settings(path)


def cmd_install(args: argparse.Namespace) -> int:
    settings_path = canonical(args.settings_path)
    try:
        data = load_settings_or_target(settings_path)
    except FileNotFoundError:
        data = {}
    except SettingsError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    if is_installed(data):
        print(f"The digital-twin hook is already installed in {settings_path}.")
        print("Nothing to do. Run `uninstall` to remove it.")
        return 0

    if not prompt_confirm("install", settings_path):
        return 1

    # After confirmation, before publishing: baseline offsets so the first
    # hook event never replays history.
    rc = run_initialize_offsets(args.source, args.state_file, args.out_dir)
    if rc != 0:
        print(
            f"ERROR: detector initialization failed (exit code {rc}); "
            "settings were not changed and installation was not completed.",
            file=sys.stderr,
        )
        return rc

    created: list[str] = []
    if "hooks" not in data:
        created.extend(["hooks", "hooks.PostToolUse"])
    elif "PostToolUse" not in data["hooks"]:
        created.append("hooks.PostToolUse")

    entry = {
        "matcher": "*",
        "hooks": [
            {
                "type": "command",
                "command": build_hook_command(args.source, args.state_file, args.out_dir),
            }
        ],
        MARKER_KEY: {
            "kind": MARKER_KIND,
            "version": MARKER_VERSION,
            "installed_at": datetime.now(timezone.utc).isoformat(),
            "source": canonical(args.source),
            "state_file": canonical(args.state_file),
            "out_dir": canonical(args.out_dir),
            "created_containers": created,
        },
    }
    data.setdefault("hooks", {}).setdefault("PostToolUse", []).append(entry)
    try:
        atomic_write_settings(settings_path, data)
    except OSError as exc:
        print(f"ERROR: could not write settings file {settings_path}: {exc}", file=sys.stderr)
        return 2
    print(f"Installed the digital-twin PostToolUse hook in {settings_path}.")
    print("The detector is incremental: it only processes new transcript bytes.")
    print("Run `/digital-twin:propose-rules` to review queued proposals.")
    print("Run `uninstall` on this script to remove the hook.")
    return 0


def cmd_uninstall(args: argparse.Namespace) -> int:
    settings_path = canonical(args.settings_path)
    try:
        data = load_settings(settings_path)
    except FileNotFoundError:
        print(f"Settings file {settings_path} does not exist; nothing to uninstall.")
        return 0
    except SettingsError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    if not prompt_confirm("uninstall", settings_path):
        return 1

    owned = marker_owned_entries(data)
    if not owned:
        print(f"The digital-twin hook is not installed in {settings_path}.")
        print("Nothing to do.")
        return 0

    created: set[str] = set()
    for entry in owned:
        marker = entry[MARKER_KEY]
        containers = marker.get("created_containers", [])
        if isinstance(containers, list):
            created.update(c for c in containers if isinstance(c, str))

    hooks = data["hooks"]
    owned_ids = {id(e) for e in owned}
    hooks["PostToolUse"] = [e for e in hooks["PostToolUse"] if id(e) not in owned_ids]
    if "hooks.PostToolUse" in created and not hooks["PostToolUse"]:
        # Only prune containers this installation introduced; user-authored
        # empty containers are preserved.
        del hooks["PostToolUse"]
    if "hooks" in created and not hooks:
        del data["hooks"]
    try:
        atomic_write_settings(settings_path, data)
    except OSError as exc:
        print(f"ERROR: could not write settings file {settings_path}: {exc}", file=sys.stderr)
        return 2
    print(f"Uninstalled the digital-twin PostToolUse hook from {settings_path}.")
    print("Unrelated settings were preserved.")
    return 0


def _add_settings_flags(parser: argparse.ArgumentParser) -> None:
    # Both subcommands consume the settings target, so both spellings are
    # exposed on each. Install-only flags are NOT added here.
    parser.add_argument(
        "--settings",
        "--settings-file",
        dest="settings_path",
        default=DEFAULT_SETTINGS,
        help="Path to the Claude Code settings JSON file (default: %(default)s).",
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="install-hook.py",
        description=(
            "Explicit, reversible installer for the digital-twin "
            "pushback-detector PostToolUse hook."
        ),
    )
    sub = ap.add_subparsers(dest="command", required=True)

    p_install = sub.add_parser(
        "install", help="Register the PostToolUse hook (prompts for confirmation)."
    )
    p_install.add_argument(
        "--source",
        default=DEFAULT_SOURCE,
        help="Projects root to watch (default: %(default)s).",
    )
    p_install.add_argument(
        "--state-file",
        default=DEFAULT_STATE_FILE,
        help="~/.claude/digital-twin/.state.json is the default detector state file.",
    )
    p_install.add_argument(
        "--out-dir",
        default=DEFAULT_OUT_DIR,
        help="Proposal queue directory (default: %(default)s).",
    )
    _add_settings_flags(p_install)
    p_install.set_defaults(func=cmd_install)

    p_uninstall = sub.add_parser(
        "uninstall", help="Remove the marker-owned PostToolUse hook entries."
    )
    _add_settings_flags(p_uninstall)
    p_uninstall.set_defaults(func=cmd_uninstall)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
