"""Frozen controller-only behavioral check; execute from standard input."""
import json
import os
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

installer = Path.cwd() / "skills/digital-twin/scripts/install-hook.py"


def invoke(path, alias="--settings"):
    return subprocess.run(
        [sys.executable, str(installer), "status", alias, str(path)],
        stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=10,
    )


def expect(path, count, alias="--settings"):
    before = path.read_bytes() if path.exists() else None
    result = invoke(path, alias)
    assert result.returncode == 0, "status did not complete successfully"
    assert json.loads(result.stdout) == {
        "version": 1, "installed": count > 0, "managedHookCount": count,
    }, "status schema or count differs"
    assert not result.stderr.strip(), "successful status emitted a diagnostic"
    assert (path.read_bytes() if path.exists() else None) == before, "settings mutated"


def snapshot(root: Path) -> dict[str, tuple[int, int, bytes | None]]:
    return {
        str(path.relative_to(root)): (
            path.lstat().st_mode, path.lstat().st_ino,
            path.read_bytes() if stat.S_ISREG(path.lstat().st_mode) else None,
        )
        for path in [root, *root.rglob("*")]
    }


def verify_unreadable(path: Path, protected: Path, root: Path, command: list[str]) -> None:
    before = snapshot(root)
    original_mode = stat.S_IMODE(protected.stat().st_mode)
    os.chmod(protected, 0)
    try:
        probe = subprocess.run(
            [sys.executable, "-c", """
import sys
from pathlib import Path
try:
    Path(sys.argv[1]).read_bytes()
except PermissionError:
    print('permission-denied')
    sys.exit(0)
sys.exit(1)
""", str(path)],
            stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=10,
        )
        assert probe.returncode == 0 and probe.stdout == "permission-denied\n" and not probe.stderr, (
            "host cannot establish permission denial; qualification is unsupported"
        )
        result = subprocess.run(
            command, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=10,
        )
        assert stat.S_IMODE(protected.stat().st_mode) == 0, "protected permissions mutated"
        assert result.returncode != 0, "unreadable settings returned success"
        assert result.stderr.strip(), "unreadable settings omitted diagnostic"
        assert result.stdout == "", "unreadable settings emitted stdout"
    finally:
        os.chmod(protected, original_mode)
    assert snapshot(root) == before, "permission check mutated filesystem"


def verify_status(root: Path) -> None:
    missing = root / "absent-parent" / "settings.json"
    expect(missing, 0)
    assert not missing.parent.exists(), "missing parent was created"
    path = root / "settings.json"
    sentinel = root / "command-ran"
    managed = {
        "digital_twin_hook": {"kind": "digital-twin/posttooluse-hook", "version": 1},
        "matcher": "*",
        "hooks": [{"type": "command", "command": "touch " + str(sentinel)}],
    }
    for count in (0, 1, 2):
        data = {"future": {"private": "do-not-disclose"}, "hooks": {
            "PostToolUse": [managed] * count + [{"hooks": [{
                "type": "command", "command": "echo unrelated",
            }]}],
        }}
        path.write_text(json.dumps(data), encoding="utf-8")
        expect(path, count, "--settings-file")
        assert not sentinel.exists(), "hook command was executed"
    for malformed in ("{", "[]", '{"hooks":[]}',
                      '{"hooks":{"PostToolUse":[{"hooks":[{"type":"command","command":1}]}]}}'):
        path.write_text(malformed, encoding="utf-8")
        before = path.read_bytes()
        result = invoke(path)
        assert result.returncode != 0 and result.stderr.strip() and not result.stdout.strip()
        assert path.read_bytes() == before, "invalid settings mutated"
    path.write_text(json.dumps({"hooks": {"PostToolUse": [managed]}}), encoding="utf-8")
    command = [sys.executable, str(installer), "status", "--settings", str(path)]
    verify_unreadable(path, path, root, command)
    parent = root / "inaccessible-parent"
    parent.mkdir()
    nested = parent / "settings.json"
    nested.write_bytes(path.read_bytes())
    command = [sys.executable, str(installer), "status", "--settings", str(nested)]
    verify_unreadable(nested, parent, root, command)


if __name__ == "__main__":
    with tempfile.TemporaryDirectory(prefix="hook-status-holdout-") as temporary:
        verify_status(Path(temporary))
    print("Frozen hook-status behavioral checks passed.")
