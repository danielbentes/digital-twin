import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createHash } from "node:crypto";
import test from "node:test";

const workflow = readFileSync(new URL("../workflows/flow-pilot-106.yml", import.meta.url), "utf8");
const revision = "e967c29082a6647a1554fdc96312a93c6f94dd6d";
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

test("preserves all frozen plan, holdout, and workflow bytes", () => {
  const frozen = {
    "pilot-106.plan.yaml": "e1c5d61d5476f0d0bbea838781ba2b018a4dc26ad63a0ff568afb1e4e87a6ee0",
    "verification/pilot-106.py": "525d4c8db3e0af07f2ee67d417232d94252b51a8d4acea2dd2270f66a72313a7",
    "workflows/pilot-106-implementation.workflow.yaml": "0f8f9e666927f6e8ed396b08c223be238a6eaf88772023fcb57a81492df5e4cc",
    "workflows/pilot-106-review.workflow.yaml": "ae79edaf815d52549eb4b411e33fab96a028eac58724e51753d608b1ef679d7d",
  };
  for (const [path, digest] of Object.entries(frozen)) {
    assert.equal(createHash("sha256").update(readFileSync(new URL(`../../.flow/${path}`, import.meta.url))).digest("hex"), digest);
  }
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
