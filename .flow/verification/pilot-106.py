"""Frozen controller-only behavioral check; execute from standard input."""
import json
import os
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


with tempfile.TemporaryDirectory(prefix="hook-status-holdout-") as temporary:
    root = Path(temporary)
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
    path.write_text("{}", encoding="utf-8")
    os.chmod(path, 0)
    try:
        result = invoke(path)
        assert result.returncode != 0 and result.stderr.strip() and not result.stdout.strip()
    finally:
        os.chmod(path, 0o600)
print("Frozen hook-status behavioral checks passed.")
