import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createHash } from "node:crypto";
import test from "node:test";

const workflow = readFileSync(new URL("../workflows/flow-pilot-106.yml", import.meta.url), "utf8");
const revision = "544aebc13bfc50879de52396062a869ca975c367";
const implementation = readFileSync(
  new URL("../../.flow/workflows/pilot-106-implementation.workflow.yaml", import.meta.url), "utf8",
);
const review = readFileSync(
  new URL("../../.flow/workflows/pilot-106-review.workflow.yaml", import.meta.url), "utf8",
);

function implementationNode(id) {
  const block = implementation.match(new RegExp(`^  - id: ${id}\\n[\\s\\S]*?(?=^  - id:|$(?![\\s\\S]))`, "m"));
  assert.ok(block, `missing implementation node ${id}`);
  return block[0];
}

function job(name) {
  const block = workflow.match(new RegExp(`^  ${name}:\\n[\\s\\S]*?(?=^  [a-z][a-z-]*:|$(?![\\s\\S]))`, "m"));
  assert.ok(block, `missing ${name} job`);
  return block[0];
}

test("retains one canonical package before both host checks and model admission", () => {
  const prepare = job("prepare");
  const verify = job("verify");
  const pilot = job("pilot");
  assert.match(workflow, new RegExp(`FLOW_SOURCE_REVISION: ${revision}`));
  assert.match(prepare, /npm run release:prepare/);
  assert.match(prepare, /if-no-files-found: error/);
  assert.match(prepare, /overwrite: false/);
  assert.match(verify, /needs: prepare/);
  assert.match(verify, /ubuntu-24\.04/);
  assert.match(verify, /macos-15-intel/);
  assert.match(verify, /npm run release:verify/);
  assert.match(pilot, /needs: \[prepare, verify\]/);
  assert.doesNotMatch(verify + pilot, /npm (?:pack|run release:prepare)/);
  assert.doesNotMatch(prepare + verify, /secrets\./);
  assert.doesNotMatch(workflow, /50e5e4c5c21bd1518ff6445a8cc3f93f5a93132e/);
});

test("each consumer fails on archive mismatch and preserves source provenance", () => {
  for (const name of ["verify", "pilot"]) {
    const block = job(name);
    assert.match(block, /EXPECTED_PACKAGE_SHA256: \$\{\{ needs\.prepare\.outputs\.archive-sha256 \}\}/);
    assert.match(block, /shasum -a 256 -c -/);
    assert.match(block, /if-no-files-found: error|download-artifact@/);
  }
  for (const name of ["prepare", "verify"]) {
    assert.match(job(name), /env -u GITHUB_SHA npm run release:(?:prepare|verify)/);
  }
  assert.doesNotMatch(workflow, /GITHUB_SHA:/);
});

test("uploads only public package files and verifies the actual pilot consumer before secrets", () => {
  const upload = job("prepare").split("- name: Retain the exact public-source package before model use")[1];
  assert.ok(upload);
  const paths = upload.match(/          path: \|\n((?:            .+\n)+)/)?.[1]
    .trim().split("\n").map((path) => path.trim());
  assert.deepEqual(paths, [
    "flow-source/release/package/synapti-flow-harness-0.1.0-alpha.4.tgz",
    "flow-source/release/package/package-release-evidence.json",
  ]);
  assert.match(upload, /overwrite: false/);
  const pilot = job("pilot");
  const beforeSecrets = pilot.split("- name: Verify evidence custody before provider use")[0];
  assert.match(beforeSecrets, /const evidence = verifyPackageReleaseArtifact\(/);
  assert.match(beforeSecrets, /expectedSourceRevision: process\.env\.FLOW_SOURCE_REVISION/);
  assert.match(beforeSecrets, /await verifyInstalledPackageRelease\(`\$\{process\.env\.RUNNER_TEMP\}\/flow-consumer\/node_modules\/@synapti\/flow-harness`, evidence\)/);
  assert.doesNotMatch(beforeSecrets, /secrets\./);
});

test("pins the option B workflows and preserves the original scope and holdout bytes", () => {
  const frozen = {
    "pilot-106.plan.yaml": "acfc60fd261f6de1898f1cc374d13ffab426c3ff3260dee5676a89885749ccdf",
    "verification/pilot-106.py": "525d4c8db3e0af07f2ee67d417232d94252b51a8d4acea2dd2270f66a72313a7",
    "workflows/pilot-106-implementation.workflow.yaml": "91f98bdb0a26c5f36fde92985058d9f2dba104c6f47d0ed854efcd0c11ab3da6",
    "workflows/pilot-106-review.workflow.yaml": "0ecf50b85fabbad9d8e3234f5418908505195c7d6335c4db2a7799a8324b12bb",
    "workflows/pilot-106-repair.workflow.yaml": "54927aef1cd235c0035a4da744d1596fa6a356a02e12167f686d5ab9569fc14f",
  };
  for (const [path, digest] of Object.entries(frozen)) {
    assert.equal(createHash("sha256").update(readFileSync(new URL(`../../.flow/${path}`, import.meta.url))).digest("hex"), digest);
  }
  const plan = readFileSync(new URL("../../.flow/pilot-106.plan.yaml", import.meta.url), "utf8");
  const originalPlan = plan.split("reviewRepair:\n")[0];
  assert.equal(createHash("sha256").update(originalPlan).digest("hex"),
    "e1c5d61d5476f0d0bbea838781ba2b018a4dc26ad63a0ff568afb1e4e87a6ee0");
});

test("retains the rerun-attempt guard and keeps exact approval after encrypted evidence", () => {
  assert.match(job("prepare"), /github\.run_attempt == 1/);
  const pilot = job("pilot");
  const evidence = pilot.indexOf("Make encrypted review evidence available");
  const approval = pilot.indexOf("Wait for exact external approval");
  assert.ok(evidence >= 0 && approval >= 0 && evidence < approval);
  assert.match(pilot, /node \.github\/scripts\/hosted-flow-pilot\.mjs approve/);
  assert.doesNotMatch(workflow, /publish_github|npm publish|gh release create/);
});

test("runs the exact host-owned pytest verifier before handoff assessment", () => {
  assert.deepEqual([...implementation.matchAll(/^  - id: (.+)$/gm)].map((match) => match[1]),
    ["implement", "verify-tests", "assess"]);
  const verifier = implementationNode("verify-tests");
  assert.match(verifier, /type: verifier\n    dependsOn: \[implement\]/);
  assert.match(verifier, /kind: command\n      command:\n        executable: python3\n        args: \[-m, pytest\]\n        timeoutMs: 300000/);
  assert.doesNotMatch(verifier, /model:|prompt:|recovery:/);
  const assessment = implementationNode("assess");
  assert.match(assessment, /dependsOn: \[implement, verify-tests\]/);
  assert.match(assessment, /nodeId: implement, field: agent\.text/);
  assert.match(assessment, /nodeId: verify-tests, field: verifier\.verdict/);
  assert.match(assessment, /nodeId: verify-tests, field: verifier\.reason/);
});

test("scopes assessment to the handoff without borrowing future acceptance proofs", () => {
  const assessment = implementationNode("assess");
  assert.match(assessment, /implementation handoff only/);
  assert.match(assessment, /host-produced pytest verdict and reason/);
  assert.match(assessment, /must remain pending/);
  assert.match(assessment, /Do not require their receipts at this stage/);
  assert.match(assessment, /Reject known failures/);
  assert.match(assessment, /inconclusive/);
});

test("keeps original node recovery and output ceilings within the smaller child budget", () => {
  assert.match(implementationNode("implement"), /recovery: \{ mode: fresh, maxAttempts: 2 \}/);
  assert.match(implementationNode("assess"), /recovery: \{ mode: fresh, maxAttempts: 2 \}/);
  assert.match(implementationNode("implement"), /maxOutputTokens: 16384\n      timeoutMs: 1200000/);
  assert.match(implementationNode("assess"), /maxOutputTokens: 4096\n      timeoutMs: 300000/);
});

test("validates the installed repair plan before credential admission", () => {
  const pilot = job("pilot");
  const validation = pilot.indexOf("Validate the approved repair plan without pilot secrets");
  const baseline = pilot.indexOf("Verify the untouched baseline in the installed sandbox");
  const credentials = pilot.indexOf("Verify evidence custody before provider use");
  assert.ok(validation >= 0 && baseline > validation && credentials > baseline);
  const step = pilot.slice(validation, baseline);
  assert.match(step, /flow-consumer\/node_modules\/\.bin\/flow" issue validate \.flow\/pilot-106\.plan\.yaml/);
  assert.match(step, /pilot-evidence\/plan-validation\.json/);
  assert.doesNotMatch(step, /secrets\.|--provider|--model/);
});

test("qualifies the untouched baseline in the installed sandbox before credential admission", () => {
  const pilot = job("pilot");
  const installed = pilot.indexOf("Install and verify the retained candidate without pilot secrets");
  const baseline = pilot.indexOf("Verify the untouched baseline in the installed sandbox");
  const credentials = pilot.indexOf("Verify evidence custody before provider use");
  assert.ok(installed >= 0 && baseline > installed && credentials > baseline);
  const step = pilot.slice(baseline, credentials);
  assert.match(step, /working-directory: target/);
  assert.match(step, /flow-consumer\/node_modules\/\.bin\/flow" run \.flow\/workflows\/pilot-106-baseline\.workflow\.yaml/);
  assert.match(step, /--runs-dir "\$RUNNER_TEMP\/pilot-evidence\/baseline-runs"/);
  assert.match(step, /> "\$RUNNER_TEMP\/pilot-evidence\/baseline-result\.json"/);
  assert.match(step, /result\.resources\.modelTokens !== 0/);
  assert.match(step, /result\.resources\.modelCostUsdMicros !== 0/);
  assert.doesNotMatch(step, /secrets\.|--provider|--model/);
  const source = readFileSync(new URL("../../.flow/workflows/pilot-106-baseline.workflow.yaml", import.meta.url), "utf8");
  assert.equal((source.match(/^  - id:/gm) ?? []).length, 1);
  assert.match(source, /type: verifier\n    verifier:\n      kind: command/);
  assert.match(source, /executable: python3\n        args: \[-m, pytest\]\n        timeoutMs: 300000/);
  assert.doesNotMatch(source, /type: agent|kind: model|kind: packaged|when:|recovery:/);
});

test("validates review reports without requiring candidate acceptance", () => {
  const validator = review.split("  - id: validate-review\n")[1];
  assert.ok(validator);
  assert.match(validator, /report validity only/);
  assert.match(validator, /Accept a valid clear report or a valid blocked report/);
  assert.match(validator, /A blocked verdict with findings is not a validation failure/);
  assert.match(validator, /does not approve the candidate or authorize publication, repair, or merge/);
  assert.match(validator, /host parser remains authoritative/);
});

test("retains strict rejection and evidence rules for invalid review reports", () => {
  const validator = review.split("  - id: validate-review\n")[1];
  assert.ok(validator);
  assert.match(validator, /Reject malformed JSON, wrong identities, missing or duplicate criteria, inconsistent verdicts, and unsupported evidence claims/);
  assert.match(validator, /Return inconclusive when evidence sufficiency cannot be established/);
  assert.match(review, /Use blocked for any finding or unsatisfied criterion/);
  assert.match(review, /Use clear only when every criterion is satisfied and findings is empty/);
  assert.match(validator, /dependsOn: \[review-result\]/);
  assert.match(validator, /nodeId: review-result, field: agent\.text/);
});
