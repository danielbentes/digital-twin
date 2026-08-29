#!/usr/bin/env python3
"""Verify the observable contract for digital-twin issue 6.

This holdout uses only public command surfaces and temporary user data. It must
fail on the frozen base and pass only after the PostToolUse integration is
installable, reversible, incremental, visible, and approval-gated.
"""

from __future__ import annotations

import json
import re
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any


ROOT = Path.cwd()
SCRIPTS = ROOT / "skills" / "digital-twin" / "scripts"
DETECTOR = SCRIPTS / "pushback-detector.py"
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
    manager_path: Path,
    action: str,
    settings: Path,
    *,
    stdin: str | None = None,
    source: Path | None = None,
    state: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    argv = [sys.executable, str(manager_path), action, "--settings", str(settings)]
    if source is not None:
        argv.extend(["--source", str(source)])
    if state is not None:
        argv.extend(["--state-file", str(state)])
    return run(argv, stdin=stdin)


def confirmation_response(prompt: str, action: str) -> str:
    """Return the explicit response requested by a supported prompt style."""
    text = prompt.lower()
    token = r"(?P<quote>['\"]?)(?P<token>[A-Za-z0-9_-]+)(?P=quote)"
    patterns = (
        rf"\b(?:type|enter)\s+(?:the\s+word\s+)?{token}\s+to\s+(?:confirm|continue|proceed)\b",
        rf"\bconfirm\b[^.\n]{{0,80}}\bby\s+(?:typing|entering)\s+(?:the\s+word\s+)?{token}",
        rf"\bto\s+confirm\b[^.\n]{{0,80}}\b(?:type|enter)\s+(?:the\s+word\s+)?{token}",
    )
    typed_responses = [
        match.group("token")
        for pattern in patterns
        for match in re.finditer(pattern, prompt, re.IGNORECASE)
    ]
    typed_response = typed_responses[-1] if typed_responses else None
    yes_confirmation = "[y/n]" in text or re.search(
        r"(?:^|[.!?]\s*)confirm\b|\bplease\s+confirm\b", text
    )
    require(
        typed_response is not None or bool(yes_confirmation),
        f"{action} did not request explicit confirmation",
    )
    return f"{typed_response}\n" if typed_response is not None else "yes\n"


def verify_confirmation_parser() -> None:
    """Exercise every supported explicit-confirmation prompt form."""
    cases = (
        ("Type 'yes' to continue", "install", "yes\n"),
        ('Type "install" to continue', "install", "install\n"),
        ("Confirm by typing PROCEED", "install", "PROCEED\n"),
        ("Type install_v2 to confirm", "install", "install_v2\n"),
        ("Confirm uninstall [y/n]", "uninstall", "yes\n"),
        ("The operation type is install. Type yes-2 to continue", "install", "yes-2\n"),
        ("Enter PROCEED to confirm installation", "install", "PROCEED\n"),
    )
    for prompt, action, expected in cases:
        require(
            confirmation_response(prompt, action) == expected,
            f"confirmation parser returned the wrong response for {prompt!r}",
        )
    for prompt in (
        "Current hook type command is valid.",
        "The selected configuration type install is available.",
    ):
        try:
            confirmation_response(prompt, "install")
        except HoldoutFailure:
            continue
        raise HoldoutFailure(
            f"confirmation parser accepted unrelated prose: {prompt!r}"
        )


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


def discover_manager() -> Path:
    matches: list[Path] = []
    for candidate in sorted(SCRIPTS.glob("*.py")):
        if candidate == DETECTOR:
            continue
        result = run([sys.executable, str(candidate), "--help"], timeout=10)
        help_text = (result.stdout + result.stderr).lower()
        if (
            result.returncode == 0
            and "install" in help_text
            and "uninstall" in help_text
        ):
            matches.append(candidate)
    require(
        len(matches) == 1,
        f"expected one public install/uninstall script, found {len(matches)}",
    )
    return matches[0]


def verify_manager_contract(work: Path) -> None:
    manager_path = discover_manager()
    install_help = run([sys.executable, str(manager_path), "install", "--help"])
    require(install_help.returncode == 0, "installer install help failed")
    require(
        "--settings" in install_help.stdout
        and "--settings-file" in install_help.stdout,
        "installer help must expose --settings and --settings-file",
    )

    settings = work / "settings.json"
    source = work / "install-history"
    project = source / "project"
    project.mkdir(parents=True)
    historical_session = project / "historical.jsonl"
    historical_session.write_text(
        "\n".join(
            [
                json_line(
                    "assistant",
                    "I will rewrite the existing settings.",
                    "2026-08-28T09:00:00Z",
                ),
                json_line(
                    "user",
                    "No, keep this pre-installation correction historical.",
                    "2026-08-28T09:00:01Z",
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    state = work / "install-state.json"
    output = work / "install-proposals"
    original: dict[str, Any] = {
        "theme": "dark",
        "permissions": {"allow": ["Read"]},
        "hooks": {
            "PostToolUse": [
                {
                    "matcher": "Write",
                    "hooks": [
                        {
                            "type": "command",
                            "command": "/usr/bin/printf",
                            "args": ["kept"],
                        }
                    ],
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

    declined = manager(
        manager_path,
        "install",
        settings,
        stdin="no\n",
        source=source,
        state=state,
    )
    require(
        settings.read_bytes() == original_bytes,
        "declined installation changed settings",
    )
    require(not state.exists(), "declined installation created detector state")
    decline_text = (declined.stdout + declined.stderr).lower()
    install_confirmation = confirmation_response(decline_text, "install")

    installed = manager(
        manager_path,
        "install",
        settings,
        stdin=install_confirmation,
        source=source,
        state=state,
    )
    require(
        installed.returncode == 0,
        f"confirmed installation failed: {installed.stderr[:300]}",
    )
    installed_value = json.loads(settings.read_text(encoding="utf-8"))
    require(
        installed_value["theme"] == original["theme"],
        "install changed an unrelated setting",
    )
    require(
        installed_value["permissions"] == original["permissions"],
        "install changed permissions",
    )
    require(
        installed_value["hooks"]["PreToolUse"] == original["hooks"]["PreToolUse"],
        "install changed another hook event",
    )
    require(
        original["hooks"]["PostToolUse"][0] in installed_value["hooks"]["PostToolUse"],
        "install removed an unrelated PostToolUse hook",
    )
    detector_references = [
        text
        for text in command_strings(installed_value)
        if "pushback-detector.py" in text
    ]
    require(
        len(detector_references) == 1,
        "install must register exactly one detector command",
    )
    detector_reference = detector_references[0]
    require(
        "||" not in detector_reference,
        "installed detector command masks a nonzero hook status",
    )
    require(
        re.search(r"(?:^|\s)2\s*>", detector_reference) is None,
        "installed detector command redirects its stderr diagnostic",
    )
    seeded_state = json.loads(state.read_text(encoding="utf-8"))
    require(
        durable_offset(seeded_state, historical_session)
        == historical_session.stat().st_size,
        "installation did not baseline existing complete session history",
    )
    require(
        not proposal_paths(output),
        "installation classified historical content or created proposals",
    )

    with historical_session.open("a", encoding="utf-8") as stream:
        stream.write(
            json_line(
                "assistant",
                "I will remove the unrelated hook.",
                "2026-08-28T09:01:00Z",
            )
            + "\n"
        )
        stream.write(
            json_line(
                "user",
                "Actually, preserve the unrelated hook.",
                "2026-08-28T09:01:01Z",
            )
            + "\n"
        )
    first_hook = run(detector_command(source, output, state))
    require(
        first_hook.returncode == 0,
        f"first post-install detector invocation failed: {first_hook.stderr[:300]}",
    )
    proposals = proposal_paths(output)
    require(len(proposals) == 1, "first hook did not process exactly one new pair")
    proposal_text = proposals[0].read_text(encoding="utf-8")
    require(
        "preserve the unrelated hook" in proposal_text.lower(),
        "first hook did not process the post-install pair",
    )
    require(
        "pre-installation correction" not in proposal_text.lower(),
        "first hook replayed pre-installation history",
    )
    require(
        "/digital-twin:propose-rules" in first_hook.stdout,
        "detector output does not use the registered proposal-review command",
    )

    before_repeat = settings.read_bytes()
    repeated = manager(
        manager_path,
        "install",
        settings,
        stdin=install_confirmation,
        source=source,
        state=state,
    )
    require(repeated.returncode == 0, "repeated confirmed installation failed")
    require(
        settings.read_bytes() == before_repeat,
        "repeated installation was not byte-idempotent",
    )

    before_declined_uninstall = settings.read_bytes()
    declined_uninstall = manager(manager_path, "uninstall", settings, stdin="no\n")
    require(
        settings.read_bytes() == before_declined_uninstall,
        "declined uninstallation changed settings",
    )
    uninstall_prompt = declined_uninstall.stdout + declined_uninstall.stderr
    uninstall_confirmation = confirmation_response(uninstall_prompt, "uninstall")
    removed = manager(manager_path, "uninstall", settings, stdin=uninstall_confirmation)
    require(
        removed.returncode == 0, f"confirmed uninstall failed: {removed.stderr[:300]}"
    )
    require(
        json.loads(settings.read_text(encoding="utf-8")) == original,
        "uninstall did not restore the original settings structure",
    )

    malformed = work / "malformed-settings.json"
    malformed.write_bytes(b'{"hooks": [')
    malformed_before = malformed.read_bytes()
    rejected = manager(manager_path, "install", malformed, stdin="yes\n")
    require(rejected.returncode != 0, "malformed settings did not fail closed")
    require(
        malformed.read_bytes() == malformed_before,
        "malformed settings were replaced or truncated",
    )
    require(
        any(
            word in (rejected.stdout + rejected.stderr).lower()
            for word in ("invalid", "malformed", "json")
        ),
        "malformed-settings failure was not clear",
    )

    malformed_structures: tuple[dict[str, Any], ...] = (
        {"hooks": {"PostToolUse": ["invalid-event"]}},
        {
            "hooks": {
                "PostToolUse": [{"matcher": "Write", "hooks": "invalid-nested-hooks"}]
            }
        },
        {
            "hooks": {
                "PostToolUse": [
                    {
                        "matcher": "Write",
                        "hooks": [{"type": "command", "command": 7}],
                    }
                ]
            }
        },
    )
    for index, malformed_value in enumerate(malformed_structures):
        malformed_nested = work / f"malformed-nested-{index}.json"
        malformed_nested.write_text(
            json.dumps(malformed_value, indent=2) + "\n", encoding="utf-8"
        )
        nested_before = malformed_nested.read_bytes()
        nested_rejected = manager(
            manager_path, "install", malformed_nested, stdin="yes\n"
        )
        require(
            nested_rejected.returncode != 0,
            f"malformed nested hook structure {index} did not fail closed",
        )
        require(
            malformed_nested.read_bytes() == nested_before,
            f"malformed nested hook structure {index} was rewritten",
        )

    canonical_parent = work / "canonical-settings-parent"
    canonical_parent.mkdir()
    lexical_project = work / "project-with-linked-claude"
    lexical_project.mkdir()
    linked_parent = lexical_project / ".claude"
    linked_parent.symlink_to(canonical_parent, target_is_directory=True)
    lexical_settings = linked_parent / "settings.local.json"
    canonical_settings = canonical_parent / "settings.local.json"
    linked_decline = manager(manager_path, "install", lexical_settings, stdin="no\n")
    require(
        str(canonical_settings) in linked_decline.stdout + linked_decline.stderr,
        "confirmation did not disclose the canonical parent-symlink target",
    )
    require(
        not canonical_settings.exists(),
        "declined canonical-target confirmation created settings",
    )


def detector_command(
    source: Path, output: Path, state: Path, *, max_proposals: int = 10
) -> list[str]:
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
        str(max_proposals),
    ]


def proposal_paths(output: Path) -> list[Path]:
    return sorted(path for path in output.glob("*.md") if path.is_file())


def durable_offset(state: dict[str, Any], session: Path) -> int:
    offsets = state.get("offsets")
    require(isinstance(offsets, dict), "detector state has no offsets object")
    canonical_session = session.resolve()
    matches = [
        value
        for key, value in offsets.items()
        if isinstance(key, str) and Path(key).resolve() == canonical_session
    ]
    require(
        len(matches) == 1,
        f"expected one canonical offset for {canonical_session}, found {len(matches)}",
    )
    offset = matches[0]
    require(
        isinstance(offset, int) and not isinstance(offset, bool) and offset >= 0,
        f"detector offset for {canonical_session} is not a nonnegative integer",
    )
    return offset


def verify_capped_proposals_are_deferred(work: Path) -> None:
    source = work / "capped-projects"
    project = source / "pilot"
    project.mkdir(parents=True)
    output = work / "capped-proposals"
    state = work / "capped-state.json"
    session = project / "session.jsonl"
    records: list[str] = []
    for index in range(3):
        records.extend(
            [
                json_line(
                    "assistant",
                    f"I will replace bounded behavior {index}.",
                    f"2026-08-28T12:0{index}:00Z",
                ),
                json_line(
                    "user",
                    f"No, preserve distinct bounded behavior {index}.",
                    f"2026-08-28T12:0{index}:01Z",
                ),
            ]
        )
    session.write_bytes(b"")
    initialized = run(
        [
            *detector_command(source, output, state, max_proposals=2),
            "--initialize-offsets",
        ]
    )
    require(
        initialized.returncode == 0,
        f"capped fixture initialization failed: {initialized.stderr[:300]}",
    )
    session.write_text("\n".join(records) + "\n", encoding="utf-8")

    command = detector_command(source, output, state, max_proposals=2)
    first = run(command)
    require(first.returncode == 0, f"capped first run failed: {first.stderr[:300]}")
    require(len(proposal_paths(output)) == 2, "first capped run did not emit two")

    second = run(command)
    require(second.returncode == 0, f"capped second run failed: {second.stderr[:300]}")
    require(
        len(proposal_paths(output)) == 3,
        "proposal cap permanently discarded a qualifying candidate",
    )
    before_third = [path.read_bytes() for path in proposal_paths(output)]
    third = run(command)
    require(third.returncode == 0, f"capped third run failed: {third.stderr[:300]}")
    require(
        [path.read_bytes() for path in proposal_paths(output)] == before_third,
        "deferred candidates were emitted more than once",
    )


def verify_untrustworthy_state_fails_closed(work: Path) -> None:
    source = work / "corrupt-state-projects"
    project = source / "pilot"
    project.mkdir(parents=True)
    output = work / "corrupt-state-proposals"
    state = work / "corrupt-state.json"
    session = project / "session.jsonl"
    session.write_text(
        "\n".join(
            [
                json_line("assistant", "Historical draft.", "2026-08-28T13:00:00Z"),
                json_line(
                    "user",
                    "No, corrupt state must not replay this.",
                    "2026-08-28T13:00:01Z",
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    state.write_bytes(b'{"offsets": {')
    state_before = state.read_bytes()

    result = run(detector_command(source, output, state))
    require(result.returncode != 0, "untrustworthy state did not fail closed")
    require(state.read_bytes() == state_before, "untrustworthy state was replaced")
    require(
        not proposal_paths(output),
        "untrustworthy state replayed historical content into proposals",
    )


def verify_malformed_record_does_not_advance(work: Path) -> None:
    source = work / "malformed-record-projects"
    project = source / "pilot"
    project.mkdir(parents=True)
    output = work / "malformed-record-proposals"
    state = work / "malformed-record-state.json"
    session = project / "session.jsonl"
    assistant = (
        json_line("assistant", "Pending before corruption.", "2026-08-28T14:00:00Z")
        + "\n"
    ).encode("utf-8")
    malformed = b'{"type":"user",broken}\n'
    trailing_user = (
        json_line(
            "user",
            "No, data after corruption cannot be silently paired.",
            "2026-08-28T14:00:01Z",
        )
        + "\n"
    ).encode("utf-8")
    session.write_bytes(assistant + malformed + trailing_user)
    state.write_text(
        json.dumps(
            {
                "offsets": {str(session.resolve()): 0},
                "seen_hashes": [],
                "pending_assistants": {},
            }
        ),
        encoding="utf-8",
    )

    result = run(detector_command(source, output, state))
    require(result.returncode != 0, "complete malformed JSONL did not fail closed")
    require(
        not proposal_paths(output), "records after malformed JSONL created a proposal"
    )
    recovered = json.loads(state.read_text(encoding="utf-8"))
    require(
        durable_offset(recovered, session) <= len(assistant),
        "detector checkpoint advanced past malformed JSONL",
    )


def verify_session_replacement_clears_pending(work: Path) -> None:
    source = work / "replacement-projects"
    project = source / "pilot"
    project.mkdir(parents=True)
    output = work / "replacement-proposals"
    state = work / "replacement-state.json"
    session = project / "session.jsonl"
    session.write_bytes(b"")
    initialized = run(
        [*detector_command(source, output, state), "--initialize-offsets"]
    )
    require(
        initialized.returncode == 0,
        f"replacement fixture initialization failed: {initialized.stderr[:300]}",
    )
    session.write_text(
        json_line(
            "assistant",
            "Old assistant that must not survive replacement. " + "x" * 600,
            "2026-08-28T15:00:00Z",
        )
        + "\n",
        encoding="utf-8",
    )
    first = run(detector_command(source, output, state))
    require(first.returncode == 0, f"pending setup failed: {first.stderr[:300]}")

    session.write_text(
        json_line(
            "user",
            "No, this reply belongs to a replacement file.",
            "2026-08-28T15:01:00Z",
        )
        + "\n",
        encoding="utf-8",
    )
    replaced = run(detector_command(source, output, state))
    require(
        replaced.returncode == 0,
        f"replacement handling failed: {replaced.stderr[:300]}",
    )
    require(
        not proposal_paths(output),
        "replacement user record paired with a stale assistant turn",
    )

    with session.open("a", encoding="utf-8") as stream:
        stream.write(
            json_line("assistant", "New assistant.", "2026-08-28T15:02:00Z") + "\n"
        )
        stream.write(
            json_line(
                "user",
                "Actually, pair only with the new assistant.",
                "2026-08-28T15:02:01Z",
            )
            + "\n"
        )
    appended = run(detector_command(source, output, state))
    require(
        appended.returncode == 0,
        f"post-replacement append failed: {appended.stderr[:300]}",
    )
    proposals = proposal_paths(output)
    require(len(proposals) == 1, "post-replacement append did not create one proposal")
    replacement_text = proposals[0].read_text(encoding="utf-8")
    require("New assistant" in replacement_text, "proposal omitted the new assistant")
    require(
        "Old assistant" not in replacement_text,
        "proposal retained assistant text from the replaced session",
    )


def verify_incremental_detector(work: Path) -> None:
    source = work / "projects"
    project = source / "pilot-project"
    memory = project / "memory"
    output = work / "proposed-rules"
    state = work / "detector-state.json"
    session = project / "session.jsonl"
    memory.mkdir(parents=True)
    memory_rule = memory / "existing.md"
    memory_rule.write_text(
        "---\nname: existing\ndescription: Keep existing behavior.\ntype: feedback\n---\n",
        encoding="utf-8",
    )
    memory_before = memory_rule.read_bytes()

    first_pair = (
        "\n".join(
            [
                json_line(
                    "assistant",
                    "I will replace the configuration.",
                    "2026-08-28T10:00:00Z",
                ),
                json_line(
                    "user",
                    "No, preserve every unrelated setting and hook.",
                    "2026-08-28T10:00:01Z",
                ),
            ]
        )
        + "\n"
    )
    session.write_text(first_pair, encoding="utf-8")
    initialized = run(
        [*detector_command(source, output, state), "--initialize-offsets"]
    )
    require(
        initialized.returncode == 0,
        f"detector initialization failed: {initialized.stderr[:300]}",
    )
    require(
        not proposal_paths(output),
        "detector initialization classified historical content",
    )
    baseline_offset = durable_offset(
        json.loads(state.read_text(encoding="utf-8")), session
    )
    require(
        baseline_offset == session.stat().st_size,
        "detector initialization did not baseline the complete record boundary",
    )

    with session.open("a", encoding="utf-8") as stream:
        stream.write(
            json_line(
                "assistant",
                "I will change the newly observed configuration.",
                "2026-08-28T10:00:02Z",
            )
            + "\n"
        )
        stream.write(
            json_line(
                "user",
                "No, preserve the newly observed setting and hook.",
                "2026-08-28T10:00:03Z",
            )
            + "\n"
        )
    first = run(detector_command(source, output, state))
    require(
        first.returncode == 0, f"first detector invocation failed: {first.stderr[:300]}"
    )
    require(
        len(proposal_paths(output)) == 1,
        "first post-baseline pushback pair did not create one proposal",
    )
    first_offset = durable_offset(
        json.loads(state.read_text(encoding="utf-8")), session
    )
    require(
        first_offset == session.stat().st_size,
        "first durable offset did not end at the complete-line boundary",
    )
    require(
        memory_rule.read_bytes() == memory_before,
        "detector wrote to memory instead of the proposal queue",
    )

    pending_assistant = json_line(
        "assistant",
        "I will automatically approve the proposed rule.",
        "2026-08-28T10:01:00Z",
    )
    with session.open("a", encoding="utf-8") as stream:
        stream.write(pending_assistant)
    partial = run(detector_command(source, output, state))
    require(
        partial.returncode == 0,
        f"partial-line detector invocation failed: {partial.stderr[:300]}",
    )
    partial_offset = durable_offset(
        json.loads(state.read_text(encoding="utf-8")), session
    )
    require(
        partial_offset == first_offset,
        "detector advanced its offset past an incomplete JSONL line",
    )
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
    require(
        second.returncode == 0,
        f"second detector invocation failed: {second.stderr[:300]}",
    )
    require(
        len(proposal_paths(output)) == 2,
        "second invocation did not process only the newly completed pair",
    )
    second_offset = durable_offset(
        json.loads(state.read_text(encoding="utf-8")), session
    )
    require(
        second_offset == session.stat().st_size,
        "second durable offset does not match the complete file",
    )
    require(
        memory_rule.read_bytes() == memory_before,
        "second detector invocation wrote to memory",
    )

    before_noop = [path.read_bytes() for path in proposal_paths(output)]
    no_op = run(detector_command(source, output, state))
    require(no_op.returncode == 0, "no-op detector invocation failed")
    require(
        [path.read_bytes() for path in proposal_paths(output)] == before_noop,
        "no-op detector invocation duplicated or changed proposals",
    )

    with session.open("a", encoding="utf-8") as stream:
        for index in range(1_000):
            stream.write(
                json_line(
                    "assistant", f"Routine result {index}.", "2026-08-28T11:00:00Z"
                )
                + "\n"
            )
            stream.write(json_line("user", "approved", "2026-08-28T11:00:01Z") + "\n")
    consumed = run(detector_command(source, output, state), timeout=60)
    require(consumed.returncode == 0, "realistic incremental fixture failed to process")
    timings: list[float] = []
    for _ in range(5):
        started = time.perf_counter()
        measured = run(detector_command(source, output, state))
        timings.append(time.perf_counter() - started)
        require(measured.returncode == 0, "latency measurement invocation failed")
    require(
        statistics.median(timings) < 0.4,
        f"median no-op hook latency exceeded 400 ms: {timings}",
    )
    require(
        max(timings) < 1.0, f"one no-op hook invocation exceeded 1 second: {timings}"
    )


def verify_public_documentation() -> None:
    for path in (STATUS_COMMAND, README):
        require(
            path.is_file(), f"missing public documentation: {path.relative_to(ROOT)}"
        )
    hook_commands = []
    for path in sorted((ROOT / "commands").glob("*.md")):
        text = path.read_text(encoding="utf-8").lower()
        if all(
            term in text for term in ("install", "uninstall", "confirm", "posttooluse")
        ):
            hook_commands.append(path)
    require(
        len(hook_commands) == 1,
        f"expected one public hook command, found {len(hook_commands)}",
    )
    hook = hook_commands[0].read_text(encoding="utf-8").lower()
    status = STATUS_COMMAND.read_text(encoding="utf-8").lower()
    readme = README.read_text(encoding="utf-8").lower()
    require(
        "digital-twin:" in hook, "hook command does not expose a public plugin command"
    )
    for term in ("install", "uninstall", "confirm", "posttooluse"):
        require(term in hook, f"hook command does not explain {term}")
    for term in ("pending", "proposal", "proposed-rules"):
        require(term in status, f"status command does not surface {term}")
    for term in ("posttooluse", "uninstall", "proposed-rules", "propose-rules"):
        require(term in readme, f"README does not explain {term}")
    no_automatic_memory_phrases = (
        "never writes to memory",
        "does not write to memory",
        "doesn't write to memory",
        "nothing is auto-written to memory",
        "nothing crosses into memory automatically",
        "nothing reaches memory without explicit /digital-twin:propose-rules approval",
    )
    require(
        any(phrase in readme for phrase in no_automatic_memory_phrases),
        "README does not state the no-automatic-memory boundary",
    )
    cadence_sentence = (
        "the posttooluse hook can run zero, one, or multiple times during an "
        "assistant turn, depending on successful matched tool uses."
    )
    require(
        cadence_sentence in readme, "README does not state the required hook cadence"
    )
    inaccurate_cadence_claims = (
        "runs after every turn",
        "runs exactly once per assistant turn",
        "runs once per assistant turn",
    )
    require(
        not any(claim in readme for claim in inaccurate_cadence_claims),
        "README incorrectly describes PostToolUse as exactly once per assistant turn",
    )
    require(
        "/digital-twin propose-rules" not in readme,
        "README uses the unregistered proposal-review command spelling",
    )


def main() -> int:
    try:
        verify_confirmation_parser()
        with tempfile.TemporaryDirectory(prefix="digital-twin-issue-6-") as directory:
            work = Path(directory)
            verify_manager_contract(work)
            verify_incremental_detector(work)
            verify_capped_proposals_are_deferred(work)
            verify_untrustworthy_state_fails_closed(work)
            verify_malformed_record_does_not_advance(work)
            verify_session_replacement_clears_pending(work)
        verify_public_documentation()
    except (
        HoldoutFailure,
        KeyError,
        json.JSONDecodeError,
        OSError,
        subprocess.TimeoutExpired,
    ) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1
    print("PASS: digital-twin issue 6 observable contract")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
