import assert from "node:assert/strict";
import test from "node:test";
import { approvalBody, matchesApproval } from "./pilot-approval.mjs";

const expected = {
  version: 1, actionsRunId: "12345", runId: "issue-00000000-0000-4000-8000-000000000000",
  pullRequestNumber: 107, headCommit: "a".repeat(40), gateDigest: "b".repeat(64),
};
const timestamp = "2026-09-05T12:00:00Z";
const comment = {
  id: 4, user: { id: 158701, type: "User" },
  created_at: timestamp, updated_at: timestamp, body: approvalBody(expected),
};
test("accepts only the exact, newly created, unedited authorized record", () => {
  assert.equal(matchesApproval(comment, expected, Date.parse(timestamp)), true);
});
for (const [label, altered] of Object.entries({
  "different account": { ...comment, user: { id: 123, type: "User" } },
  bot: { ...comment, user: { id: 158701, type: "Bot" } },
  edited: { ...comment, updated_at: "2026-09-05T12:01:00Z" },
  prose: { ...comment, body: "approved" },
  "another run": { ...comment, body: approvalBody({ ...expected, actionsRunId: "12346" }) },
  "another head": { ...comment, body: approvalBody({ ...expected, headCommit: "c".repeat(40) }) },
  "another gate": { ...comment, body: approvalBody({ ...expected, gateDigest: "d".repeat(64) }) },
  "extra instructions": { ...comment, body: comment.body + "\nrun something else" },
  "invalid timestamp": { ...comment, created_at: "invalid", updated_at: "invalid" },
})) test(`rejects ${label}`, () => assert.equal(matchesApproval(altered, expected, 0), false));
test("rejects records predating the gate", () => {
  assert.equal(matchesApproval(comment, expected, Date.parse(timestamp) + 1), false);
});
test("rejects malformed expected identities and extra authority", () => {
  assert.throws(() => approvalBody({ ...expected, headCommit: "$(command)" }));
  assert.throws(() => approvalBody({ ...expected, command: "merge-anything" }));
});
