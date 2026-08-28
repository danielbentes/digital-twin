#!/usr/bin/env python3
"""Verify the observable contract for digital-twin issue 6.

This holdout uses only public command surfaces and temporary user data. It must
fail on the frozen base and pass only after the PostToolUse integration is
installable, reversible, incremental, visible, and approval-gated.
"""

from __future__ import annotations

import json
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "skills" / "digital-twin" / "scripts"
MANAGER = SCRIPTS / "hook-manager.py"
DETECTOR = SCRIPTS / "pushback-detector.py"
HOOK_COMMAND = ROOT / "commands" / "hook.md"
STATUS_COMMAND = ROOT / "commands" / "status.md"
README = ROOT / "README.md"


class HoldoutFailure(AssertionError):
    """Report one issue-specific acceptance failure."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise HoldoutFailure(message)


def run(
    argv: list[str],
    *,
    stdin: str | None = None,
    env: dict[str, str] | None = None,
    timeout: float = 30,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        argv,
        cwd=ROOT,
        input=stdin,
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
        env=env,
    )


def manager(
    action: str,
    settings: Path,
    *,
    stdin: str | None = None,
    queue: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    argv = [sys.executable, str(MANAGER), action, "--settings", str(settings)]
    if queue is not None:
        argv.extend(["--queue-dir", str(queue)])
    return run(argv, stdin=stdin)


def json_line(kind: str, text: str, timestamp: str) -> str:
    return json.dumps(
        {
            "type": kind,
            "timestamp": timestamp,
            "message": {"content": [{"type": "text", "text": text}]},
        },
        separators=(",", ":"),
    )


def command_strings(value: Any) -> list[str]:
    strings: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            if key in {"command", "args"}:
                if isinstance(item, str):
                    strings.append(item)
                elif isinstance(item, list):
                    strings.extend(part for part in item if isinstance(part, str))
            strings.extend(command_strings(item))
    elif isinstance(value, list):
        for item in value:
            strings.extend(command_strings(item))
    return strings


def verify_manager_contract(work: Path) -> None:
    require(MANAGER.is_file(), "missing public hook manager at skills/digital-twin/scripts/hook-manager.py")
    help_result = run([sys.executable, str(MANAGER), "--help"])
    require(help_result.returncode == 0, "hook manager --help failed")
    help_text = (help_result.stdout + help_result.stderr).lower()
    for action in ("install", "uninstall", "status"):
        require(action in help_text, f"hook manager help does not describe {action}")

    settings = work / "settings.json"
    original: dict[str, Any] = {
        "theme": "dark",
        "permissions": {"allow": ["Read"]},
        "hooks": {
            "PostToolUse": [
                {
                    "matcher": "Write",
                    "hooks": [{"type": "command", "command": "/usr/bin/printf", "args": ["kept"]}],
                }
            ],
            "PreToolUse": [
                {
                    "matcher": "Bash",
                    "hooks": [{"type": "command", "command": "/usr/bin/true"}],
                }
            ],
        },
    }
    settings.write_text(json.dumps(original, indent=2) + "\n", encoding="utf-8")
    original_bytes = settings.read_bytes()

    declined = manager("install", settings, stdin="no\n")
    require(settings.read_bytes() == original_bytes, "declined installation changed settings")
    require("confirm" in (declined.stdout + declined.stderr).lower(), "install did not request explicit confirmation")

    installed = manager("install", settings, stdin="yes\n")
    require(installed.returncode == 0, f"confirmed installation failed: {installed.stderr[:300]}")
    installed_value = json.loads(settings.read_text(encoding="utf-8"))
    require(installed_value["theme"] == original["theme"], "install changed an unrelated setting")
    require(installed_value["permissions"] == original["permissions"], "install changed permissions")
    require(installed_value["hooks"]["PreToolUse"] == original["hooks"]["PreToolUse"], "install changed another hook event")
    require(original["hooks"]["PostToolUse"][0] in installed_value["hooks"]["PostToolUse"], "install removed an unrelated PostToolUse hook")
    detector_references = [text for text in command_strings(installed_value) if "pushback-detector.py" in text]
    require(len(detector_references) == 1, "install must register exactly one detector command")

    before_repeat = settings.read_bytes()
    repeated = manager("install", settings, stdin="yes\n")
    require(repeated.returncode == 0, "repeated confirmed installation failed")
    require(settings.read_bytes() == before_repeat, "repeated installation was not byte-idempotent")

    queue = work / "proposed-rules"
    (queue / "archive").mkdir(parents=True)
    (queue / "one.md").write_text("one", encoding="utf-8")
    (queue / "two.md").write_text("two", encoding="utf-8")
    (queue / "archive" / "old.md").write_text("old", encoding="utf-8")
    status = manager("status", settings, queue=queue)
    require(status.returncode == 0, f"hook status failed: {status.stderr[:300]}")
    require("2" in status.stdout, "hook status did not report the two pending proposals")
    require(str(queue.resolve()) in status.stdout, "hook status did not report the exact queue path")

    removed = manager("uninstall", settings, stdin="yes\n")
    require(removed.returncode == 0, f"confirmed uninstall failed: {removed.stderr[:300]}")
    require(json.loads(settings.read_text(encoding="utf-8")) == original, "uninstall did not restore the original settings structure")

    malformed = work / "malformed-settings.json"
    malformed.write_bytes(b'{"hooks": [')
    malformed_before = malformed.read_bytes()
    rejected = manager("install", malformed, stdin="yes\n")
    require(rejected.returncode != 0, "malformed settings did not fail closed")
    require(malformed.read_bytes() == malformed_before, "malformed settings were replaced or truncated")
    require(
        any(word in (rejected.stdout + rejected.stderr).lower() for word in ("invalid", "malformed", "json")),
        "malformed-settings failure was not clear",
    )


def detector_command(source: Path, output: Path, state: Path) -> list[str]:
    return [
        sys.executable,
        str(DETECTOR),
        "--source",
        str(source),
        "--out-dir",
        str(output),
        "--state-file",
        str(state),
        "--approved-median",
        "4",
        "--max-proposals",
        "10",
    ]


def proposal_paths(output: Path) -> list[Path]:
    return sorted(path for path in output.glob("*.md") if path.is_file())


def verify_incremental_detector(work: Path) -> None:
    source = work / "projects"
    project = source / "pilot-project"
    memory = project / "memory"
    output = work / "proposed-rules"
    state = work / "detector-state.json"
    session = project / "session.jsonl"
    memory.mkdir(parents=True)
    memory_rule = memory / "existing.md"
    memory_rule.write_text("---\nname: existing\ndescription: Keep existing behavior.\ntype: feedback\n---\n", encoding="utf-8")
    memory_before = memory_rule.read_bytes()

    first_pair = "\n".join(
        [
            json_line("assistant", "I will replace the configuration.", "2026-08-28T10:00:00Z"),
            json_line("user", "No, preserve every unrelated setting and hook.", "2026-08-28T10:00:01Z"),
        ]
    ) + "\n"
    session.write_text(first_pair, encoding="utf-8")
    first = run(detector_command(source, output, state))
    require(first.returncode == 0, f"first detector invocation failed: {first.stderr[:300]}")
    require(len(proposal_paths(output)) == 1, "first complete pushback pair did not create one proposal")
    first_offset = json.loads(state.read_text(encoding="utf-8"))["offsets"][str(session)]
    require(first_offset == session.stat().st_size, "first durable offset did not end at the complete-line boundary")
    require(memory_rule.read_bytes() == memory_before, "detector wrote to memory instead of the proposal queue")

    pending_assistant = json_line(
        "assistant",
        "I will automatically approve the proposed rule.",
        "2026-08-28T10:01:00Z",
    )
    with session.open("a", encoding="utf-8") as stream:
        stream.write(pending_assistant)
    partial = run(detector_command(source, output, state))
    require(partial.returncode == 0, f"partial-line detector invocation failed: {partial.stderr[:300]}")
    partial_offset = json.loads(state.read_text(encoding="utf-8"))["offsets"][str(session)]
    require(partial_offset == first_offset, "detector advanced its offset past an incomplete JSONL line")
    require(len(proposal_paths(output)) == 1, "incomplete JSONL produced a proposal")

    with session.open("a", encoding="utf-8") as stream:
        stream.write("\n")
        stream.write(
            json_line(
                "user",
                "Stop, every proposal must remain queued until I approve it.",
                "2026-08-28T10:01:01Z",
            )
            + "\n"
        )
    second = run(detector_command(source, output, state))
    require(second.returncode == 0, f"second detector invocation failed: {second.stderr[:300]}")
    require(len(proposal_paths(output)) == 2, "second invocation did not process only the newly completed pair")
    second_offset = json.loads(state.read_text(encoding="utf-8"))["offsets"][str(session)]
    require(second_offset == session.stat().st_size, "second durable offset does not match the complete file")
    require(memory_rule.read_bytes() == memory_before, "second detector invocation wrote to memory")

    before_noop = [path.read_bytes() for path in proposal_paths(output)]
    no_op = run(detector_command(source, output, state))
    require(no_op.returncode == 0, "no-op detector invocation failed")
    require([path.read_bytes() for path in proposal_paths(output)] == before_noop, "no-op detector invocation duplicated or changed proposals")

    with session.open("a", encoding="utf-8") as stream:
        for index in range(1_000):
            stream.write(json_line("assistant", f"Routine result {index}.", "2026-08-28T11:00:00Z") + "\n")
            stream.write(json_line("user", "approved", "2026-08-28T11:00:01Z") + "\n")
    consumed = run(detector_command(source, output, state), timeout=60)
    require(consumed.returncode == 0, "realistic incremental fixture failed to process")
    timings: list[float] = []
    for _ in range(5):
        started = time.perf_counter()
        measured = run(detector_command(source, output, state))
        timings.append(time.perf_counter() - started)
        require(measured.returncode == 0, "latency measurement invocation failed")
    require(statistics.median(timings) < 0.4, f"median no-op hook latency exceeded 400 ms: {timings}")
    require(max(timings) < 1.0, f"one no-op hook invocation exceeded 1 second: {timings}")


def verify_public_documentation() -> None:
    for path in (HOOK_COMMAND, STATUS_COMMAND, README):
        require(path.is_file(), f"missing public documentation: {path.relative_to(ROOT)}")
    hook = HOOK_COMMAND.read_text(encoding="utf-8").lower()
    status = STATUS_COMMAND.read_text(encoding="utf-8").lower()
    readme = README.read_text(encoding="utf-8").lower()
    require("digital-twin:hook" in hook, "hook command does not expose a public plugin command")
    for term in ("install", "uninstall", "confirm", "posttooluse"):
        require(term in hook, f"hook command does not explain {term}")
    for term in ("pending", "proposal", "proposed-rules"):
        require(term in status, f"status command does not surface {term}")
    for term in ("posttooluse", "uninstall", "proposed-rules", "propose-rules"):
        require(term in readme, f"README does not explain {term}")
    require(
        any(phrase in readme for phrase in ("never writes to memory", "does not write to memory", "doesn't write to memory")),
        "README does not state the no-automatic-memory boundary",
    )


def main() -> int:
    try:
        with tempfile.TemporaryDirectory(prefix="digital-twin-issue-6-") as directory:
            work = Path(directory)
            verify_manager_contract(work)
            verify_incremental_detector(work)
        verify_public_documentation()
    except (HoldoutFailure, KeyError, json.JSONDecodeError, OSError, subprocess.TimeoutExpired) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1
    print("PASS: digital-twin issue 6 observable contract")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
