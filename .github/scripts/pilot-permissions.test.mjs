import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import test from "node:test";

const root = fileURLToPath(new URL("../../", import.meta.url));

function check(kind, behavior) {
  const result = spawnSync("python3", ["-c", String.raw`
import runpy
import sys
import tempfile
from pathlib import Path

verify = runpy.run_path('.flow/verification/pilot-106.py')['verify_unreadable']
with tempfile.TemporaryDirectory(prefix='pilot-permission-control-') as temporary:
    root = Path(temporary)
    parent = root / 'settings-parent'
    parent.mkdir()
    settings = parent / 'settings.json'
    settings.write_text('{}', encoding='utf-8')
    protected = settings if sys.argv[1] == 'file' else parent
    if sys.argv[1] == 'accessible':
        protected = root / 'unrelated'
        protected.touch()
    original_mode = protected.stat().st_mode & 0o777
    if sys.argv[2] == 'loader':
        command = [sys.executable, 'skills/digital-twin/scripts/install-hook.py',
                   'uninstall', '--settings', str(settings)]
    else:
        programs = {
            'false-success': 'print("{}")',
            'silent-error': 'raise SystemExit(1)',
            'whitespace-success': 'import sys; print(" "); sys.stderr.write("error"); sys.exit(1)',
            'permission-mutation': 'import os,sys; os.chmod(sys.argv[1], 0o700); sys.stderr.write("error"); sys.exit(1)',
            'extra-file': 'import pathlib,sys; pathlib.Path(sys.argv[2], "unexpected").touch(); sys.stderr.write("error"); sys.exit(1)',
            'contents-mutation': 'import os,pathlib,sys; os.chmod(sys.argv[1], 0o700); pathlib.Path(sys.argv[3]).write_text("changed"); os.chmod(sys.argv[1], 0); sys.stderr.write("error"); sys.exit(1)',
            'file-replacement': 'import os,pathlib,sys; os.chmod(sys.argv[1], 0o700); p=pathlib.Path(sys.argv[2], "replacement"); p.write_text("{}"); os.replace(p, sys.argv[3]); os.chmod(sys.argv[1], 0); sys.stderr.write("error"); sys.exit(1)',
        }
        command = [sys.executable, '-c', programs[sys.argv[2]], str(protected), str(root), str(settings)]
    try:
        verify(settings, protected, root, command)
    finally:
        assert protected.stat().st_mode & 0o777 == original_mode
        if sys.argv[1] == 'accessible':
            assert not (root / 'unexpected').exists(), 'command ran without denied access'
`, kind, behavior], { cwd: root, encoding: "utf8", timeout: 30000, env: { ...process.env, PYTHONDONTWRITEBYTECODE: "1" } });
  assert.equal(result.error, undefined);
  return result;
}

for (const kind of ["file", "parent"]) {
  test(`accepts the real loader's fail-closed ${kind} error and restores permissions`, () => {
    const result = check(kind, "loader");
    assert.equal(result.status, 0, result.stderr);
  });
  for (const [behavior, expected] of [
    ["false-success", "unreadable settings returned success"],
    ["silent-error", "unreadable settings omitted diagnostic"],
    ["whitespace-success", "unreadable settings emitted stdout"],
    ["permission-mutation", "protected permissions mutated"],
    ["extra-file", "permission check mutated filesystem"],
    ["contents-mutation", "permission check mutated filesystem"],
    ["file-replacement", "permission check mutated filesystem"],
  ]) {
    test(`rejects ${behavior} for denied ${kind} access`, () => {
      const result = check(kind, behavior);
      assert.notEqual(result.status, 0);
      assert.ok(result.stderr.includes(expected), result.stderr);
    });
  }
}

test("rejects unsupported permission coverage before invoking the candidate", () => {
  const result = check("accessible", "extra-file");
  assert.notEqual(result.status, 0);
  assert.ok(result.stderr.includes("host cannot establish permission denial"), result.stderr);
  assert.ok(!result.stderr.includes("command ran without denied access"), result.stderr);
});
