import assert from "node:assert/strict";
import { mkdtemp, readFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";
import { failureRecord, writeInvocationRecord } from "./pilot-invocation-record.mjs";

test("run and approval records survive together and cannot be overwritten", async () => {
  const directory = await mkdtemp(join(tmpdir(), "flow-pilot-record-test-"));
  try {
    await writeInvocationRecord(directory, "run", 1, "success", '{"phase":"run"}');
    await writeInvocationRecord(directory, "approve", 1, "success", '{"phase":"approve"}');
    await assert.rejects(writeInvocationRecord(directory, "run", 1, "success", "overwrite"));
    assert.equal(await readFile(join(directory, "run-1-success.json"), "utf8"), '{"phase":"run"}');
    assert.equal(await readFile(join(directory, "approve-1-success.json"), "utf8"), '{"phase":"approve"}');
    await assert.rejects(writeInvocationRecord(directory, "../escape", 1, "success", "bad"));
  } finally {
    await rm(directory, { recursive: true, force: true });
  }
});
test("empty-output timeouts retain their cause without unsafe error messages", () => {
  const record = JSON.parse(failureRecord({ code: "ETIMEDOUT", signal: "SIGTERM", killed: true,
    message: "must-not-be-copied" }, ["issue", "run"]));
  assert.deepEqual(record, { args: ["issue", "run"], code: "ETIMEDOUT", signal: "SIGTERM",
    killed: true, stdout: "", stderr: "" });
});
test("ordinary command exits and spawn failures remain distinguishable", () => {
  assert.equal(JSON.parse(failureRecord({ code: 2 }, [])).code, 2);
  assert.equal(JSON.parse(failureRecord({ code: "ENOENT" }, [])).code, "ENOENT");
  assert.equal(JSON.parse(failureRecord({ code: "secret value" }, [])).code, null);
});
