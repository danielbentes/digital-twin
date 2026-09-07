import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const read = (path) => readFileSync(new URL(`../../${path}`, import.meta.url), "utf8");
const plan = read(".flow/pilot-106.plan.yaml");
const implementation = read(".flow/workflows/pilot-106-implementation.workflow.yaml");
const review = read(".flow/workflows/pilot-106-review.workflow.yaml");
const repairPath = ".flow/workflows/pilot-106-repair.workflow.yaml";

test("requires independent permission evidence without expanding reviewer authority", () => {
  const agent = review.split("  - id: validate-review\n")[0];
  assert.match(agent, /absent paths separately from unreadable files and inaccessible existing parent directories/);
  assert.match(agent, /existence or access probe is not evidence of absence/);
  assert.match(agent, /permission tests establish denial independently of the candidate result/);
  assert.match(agent, /file-read denial from directory-traversal denial/);
  assert.match(agent, /tools: \[read, ls\]/);
  assert.deepEqual([...review.matchAll(/^  - id: (.+)$/gm)].map((entry) => entry[1]),
    ["review-result", "validate-review"]);
});

function budget(source, header = "budget:", indent = "  ") {
  const start = source.indexOf(`${header}\n`);
  assert.notEqual(start, -1, `missing ${header}`);
  const entries = source.slice(start + header.length + 1).split("\n");
  const result = {};
  for (const line of entries) {
    if (!line.startsWith(indent) || line.startsWith(`${indent} `)) break;
    const match = line.match(/^\s+(max[A-Za-z]+): ([0-9.]+)$/);
    assert.ok(match, `invalid budget line: ${line}`);
    assert.equal(Object.hasOwn(result, match[1]), false);
    result[match[1]] = Number(match[2]);
  }
  return result;
}

test("freezes option B's smaller child allowances and unchanged aggregate resource pools", () => {
  assert.deepEqual(budget(implementation), {
    maxNodeStarts: 4, maxModelTokens: 500000, maxCostUsd: 1,
    maxExecutionMs: 900000, maxArtifactBytes: 4194304,
  });
  assert.deepEqual(budget(review), {
    maxNodeStarts: 4, maxModelTokens: 200000, maxCostUsd: 0.4,
    maxExecutionMs: 480000, maxArtifactBytes: 3145728,
  });
  assert.deepEqual(budget(read(repairPath)), {
    maxNodeStarts: 4, maxModelTokens: 250000, maxCostUsd: 0.5,
    maxExecutionMs: 600000, maxArtifactBytes: 2097152,
  });
  const policy = plan.split("\nreviewRepair:\n")[1];
  assert.ok(policy, "missing approved review repair policy");
  assert.deepEqual(budget(policy, "    implementation:", "      "), {
    maxNodeStarts: 10, maxModelTokens: 1000000, maxCostUsdMicros: 2000000,
    maxExecutionMs: 1800000, maxArtifactBytes: 8388608,
  });
  assert.deepEqual(budget(policy, "    review:", "      "), {
    maxNodeStarts: 10, maxModelTokens: 500000, maxCostUsdMicros: 1000000,
    maxExecutionMs: 1200000, maxArtifactBytes: 8388608,
  });
});

test("permits exactly one eligible repair cycle and retains every mandatory stop", () => {
  const policy = plan.split("\nreviewRepair:\n")[1];
  assert.ok(policy);
  assert.match(policy, /  version: 1\n  mode: preauthorized\n/);
  assert.match(policy, /  workflow: \.flow\/workflows\/pilot-106-repair\.workflow\.yaml\n  resultNode: repair-result\n  maxCycles: 1\n/);
  assert.match(policy, /  eligibleClasses: \[review-findings, unsatisfied-criteria\]/);
  for (const condition of ["disputed", "unchangedTree", "repeatedTree", "uncertainUsage", "uncertainEffects"]) {
    assert.match(policy, new RegExp(`^    ${condition}: stop$`, "m"));
  }
  assert.match(plan, /blockingSeverities: \[P1, P2, P3\]/);
});

test("maps every original criterion unchanged to the terminal repair disposition verifier", () => {
  const repair = read(repairPath);
  const criteria = (source) => [...source.matchAll(/^    - id: (.+)\n      description: (.+)\n      verifier: \{ nodeId: (.+) \}$/gm)];
  const original = criteria(implementation);
  const repaired = criteria(repair);
  assert.equal(original.length, 5);
  assert.deepEqual(repaired.map((entry) => entry.slice(1, 3)), original.map((entry) => entry.slice(1, 3)));
  assert.ok(repaired.every((entry) => entry[3] === "validate-repair"));
  assert.deepEqual([...repair.matchAll(/^  - id: (.+)$/gm)].map((entry) => entry[1]),
    ["repair-result", "validate-repair"]);
  assert.match(repair, /dependsOn: \[repair-result\]/);
  assert.match(repair, /nodeId: repair-result, field: agent\.text/);
  assert.equal((repair.match(/recovery: \{ mode: fresh, maxAttempts: 2 \}/g) ?? []).length, 2);
  assert.doesNotMatch(repair, /kind: command|when:|loopGuard:|optimizationGuard:/);
});

test("preserves changed and disputed disposition authority without waiving later gates", () => {
  const repair = read(repairPath);
  assert.match(repair, /expectedResultBinding/);
  assert.match(repair, /version, repairContextDigest, candidateHead, and reviewReportDigest/);
  assert.match(repair, /Do not calculate/);
  assert.match(repair, /addressedFindingIds.*addressedCriterionIds/);
  assert.match(repair, /disputedFindingIds.*disputedCriterionIds.*reason/);
  const validator = repair.split("  - id: validate-repair\n")[1];
  assert.ok(validator);
  assert.match(validator, /Accept a valid changed result or a valid disputed result/);
  assert.match(validator, /Do not require pytest or other candidate checks to pass/);
  assert.match(validator, /host parser remains authoritative/);
  assert.match(repair, /No network, Git, GitHub, credentials, private holdout, publication, or merge authority/);
});
