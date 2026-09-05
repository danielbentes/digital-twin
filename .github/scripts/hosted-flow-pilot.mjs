import { execFile } from "node:child_process";
import { randomUUID } from "node:crypto";
import { appendFile, mkdir, readdir, writeFile } from "node:fs/promises";
import { join, resolve } from "node:path";
import { promisify } from "node:util";
import { setTimeout as delay } from "node:timers/promises";
import { approvalBody, matchesApproval } from "./pilot-approval.mjs";
import { failureRecord, writeInvocationRecord } from "./pilot-invocation-record.mjs";

const execute = promisify(execFile);
const cwd = process.cwd();
const flow = resolve(process.env.FLOW_PILOT_BINARY);
const evidence = resolve(process.env.FLOW_PILOT_EVIDENCE);
const issueUrl = "https://github.com/danielbentes/digital-twin/issues/106";
const parameters = [issueUrl, "--plan", ".flow/pilot-106.plan.yaml",
  "--provider", "openrouter", "--model", "z-ai/glm-5.3-flash"];
const controlPath = "repos/synaptiai/flow-harness/issues/201/comments";
const mode = process.argv[2];
const deadline = Date.now() + (mode === "run" ? 90 : 30) * 60_000;
let sequence = 0;
let runId;
let lastPhase;

async function invoke(binary, args, timeout = 60_000) {
  return execute(binary, args, { cwd, env: process.env, timeout, maxBuffer: 8 * 1024 * 1024 });
}

async function capture(args, timeout = 60_000) {
  const id = ++sequence;
  try {
    const result = await invoke(flow, args, timeout);
    await writeInvocationRecord(evidence, mode, id, "success", result.stdout);
    return JSON.parse(result.stdout);
  } catch (error) {
    await writeInvocationRecord(evidence, mode, id, "failure", failureRecord(error, args));
    // Never log raw command output, provider errors, or process arguments.
    throw new Error(`Installed Flow invocation ${id} failed; inspect encrypted evidence`);
  }
}

async function observe() {
  if (!runId) {
    const entries = await readdir(join(cwd, ".flow/issue-runs")).catch(() => []);
    const runs = entries.filter((name) => /^issue-[0-9a-f-]{36}$/.test(name));
    if (runs.length > 1) throw new Error("More than one pilot run exists");
    runId = runs[0];
  }
  if (!runId) return;
  const state = await capture(["issue", "inspect", runId]);
  if (state.phase !== lastPhase) {
    lastPhase = state.phase;
    console.log(JSON.stringify({ runId, phase: state.phase, sequence: state.sequence }));
    await appendFile(process.env.GITHUB_STEP_SUMMARY,
      `\nFlow run \`${runId}\`: \`${state.phase}\`.\n`);
  }
  return state;
}

async function lifecycle(args) {
  let inspecting = false;
  const timer = setInterval(async () => {
    if (inspecting) return;
    inspecting = true;
    try { await observe(); } catch { /* The next synchronous observation is authoritative. */ }
    finally { inspecting = false; }
  }, 30_000);
  try {
    await capture(args, Math.max(1, deadline - Date.now()));
  } finally {
    clearInterval(timer);
  }
  return observe();
}

async function waitForApproval(state) {
  const notBefore = Date.now();
  const expected = {
    version: 1, actionsRunId: process.env.GITHUB_RUN_ID, runId,
    pullRequestNumber: state.mergeApproval.pullRequestNumber,
    headCommit: state.mergeApproval.headCommit,
    gateDigest: state.mergeApproval.gateDigest,
  };
  const body = approvalBody(expected);
  console.log("Exact approval required on synaptiai/flow-harness PR 201:\n" + body);
  await appendFile(process.env.GITHUB_STEP_SUMMARY,
    `\nReview the exact candidate, then post this record on Flow PR 201:\n\n\`\`\`text\n${body}\n\`\`\`\n`);
  while (Date.now() < deadline) {
    const query = `${controlPath}?since=${encodeURIComponent(new Date(notBefore).toISOString())}&per_page=100`;
    const result = await invoke("gh", ["api", query]);
    const comments = JSON.parse(result.stdout);
    if (!Array.isArray(comments) || comments.length >= 100) {
      throw new Error("Approval observation exceeded its bound");
    }
    const match = comments.find((comment) => matchesApproval(comment, expected, notBefore));
    if (match) {
      const fresh = JSON.parse((await invoke("gh", ["api",
        `repos/synaptiai/flow-harness/issues/comments/${match.id}`])).stdout);
      if (!matchesApproval(fresh, expected, notBefore)) throw new Error("Approval changed");
      await writeFile(join(evidence, "approval.json"), JSON.stringify(fresh), { mode: 0o600 });
      return lifecycle(["issue", "merge", runId, "--actor", "github:danielbentes",
        "--expected-pr", String(expected.pullRequestNumber), "--expected-head", expected.headCommit,
        "--expected-gate-digest", expected.gateDigest, "--command-id", randomUUID()]);
    }
    await delay(30_000);
  }
  throw new Error("Exact approval deadline expired; no merge was authorized");
}

try {
  if (process.platform !== "linux" || process.arch !== "x64" ||
      process.env.GITHUB_REPOSITORY !== "danielbentes/digital-twin" ||
      process.env.GITHUB_REF !== "refs/heads/main" || process.env.GITHUB_RUN_ATTEMPT !== "1") {
    throw new Error("Pilot host admission failed");
  }
  await mkdir(evidence, { recursive: true, mode: 0o700 });
  if (mode === "run") {
    await capture(["issue", "validate", ".flow/pilot-106.plan.yaml"]);
    await capture(["issue", "doctor", ...parameters]);
    let state = await lifecycle(["issue", "run", ...parameters, "--command-id", randomUUID()]);
    while (state?.phase === "waiting_for_ci" && Date.now() < deadline) {
      await delay(30_000);
      state = await lifecycle(["issue", "resume", runId, "--command-id", randomUUID()]);
    }
    if (state?.phase !== "merge_approval_required" || !state.mergeApproval) {
      throw new Error("Pilot stopped before the merge gate; analyze evidence before another attempt");
    }
    await writeFile(join(evidence, "public-gate.json"), JSON.stringify(state), { mode: 0o600 });
  } else if (mode === "approve") {
    const state = await observe();
    if (state?.phase !== "merge_approval_required" || !state.mergeApproval) {
      throw new Error("The durable run is not awaiting exact approval");
    }
    const final = await waitForApproval(state);
    if (final?.phase !== "merged") throw new Error("Post-merge proof is incomplete");
    await writeFile(join(evidence, "public-final.json"), JSON.stringify(final), { mode: 0o600 });
    console.log(JSON.stringify(final));
  } else throw new Error("Specify run or approve");
} catch (error) {
  console.error(error instanceof Error ? error.message : "Pilot stopped");
  process.exitCode = 1;
}
