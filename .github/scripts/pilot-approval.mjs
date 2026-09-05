// Pilot-only approval transport. This is not a Flow remote-control API.
export const APPROVER_ID = 158701;
export const PREFIX = "FLOW_PILOT_APPROVAL_V1\n";

export function approvalBody(expected) {
  if (
    expected.version !== 1 ||
    !/^[1-9][0-9]{0,19}$/.test(expected.actionsRunId) ||
    !/^issue-[0-9a-f-]{36}$/.test(expected.runId) ||
    !Number.isSafeInteger(expected.pullRequestNumber) || expected.pullRequestNumber < 1 ||
    !/^[0-9a-f]{40}$/.test(expected.headCommit) ||
    !/^[0-9a-f]{64}$/.test(expected.gateDigest) ||
    Object.keys(expected).sort().join(",") !==
      "actionsRunId,gateDigest,headCommit,pullRequestNumber,runId,version"
  ) throw new Error("Invalid exact approval identity");
  return PREFIX + JSON.stringify(expected);
}

export function matchesApproval(comment, expected, notBefore) {
  return comment?.user?.id === APPROVER_ID && comment.user.type === "User" &&
    Number.isSafeInteger(comment.id) && comment.id > 0 &&
    comment.created_at === comment.updated_at &&
    Number.isFinite(Date.parse(comment.created_at)) &&
    Date.parse(comment.created_at) >= notBefore &&
    comment.body === approvalBody(expected);
}
