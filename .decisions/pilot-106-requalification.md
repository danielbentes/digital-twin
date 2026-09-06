# Issue 106 replacement qualification

Date: 2026-09-06. User authorized one replacement attempt with the existing OpenRouter key and
unchanged model budget ceilings. Preparation does not implement the target behavior.

## Frozen controls

- Flow source: `e967c29082a6647a1554fdc96312a93c6f94dd6d`; all three hosted checks passed.
- Starting target base: `7788170fe4d261865cc77a6aa198308217cef752`; issue 106 remains open.
- Freeze the reviewed preparation merge as the new target base before dispatch.
- Preserve the issue, plan, holdout, implementation/review workflows, model, and budget bytes.
- One dispatch only. Inspect uncertain dispatch outcomes rather than retrying. No workflow rerun.
- Keep candidate merge behind a separate exact run/head/gate approval after evidence review.
- No immutable release or npm publication is part of preparation or pilot execution.

## Alternatives and decision

1. Retain the archive in the existing pilot job, verify macOS afterward. Smallest change, but
   cannot enforce both host checks before model use.
2. Encrypt the public package with private evidence. Preserves bytes but creates unnecessary
   key dependence and exposes the evidence key to the second host.
3. Selected: prepare one canonical archive, verify that archive on Ubuntu 24.04 x64 and macOS 15
   Intel, then install the same bytes for one Ubuntu pilot. More job wiring, but admission is explicit.

Reuse Flow's release preparation and verification scripts without publication or attestation.
Their source identity prefers GITHUB_SHA. Remove the inherited variable only from package command
child processes so the scripts resolve the verified Flow checkout's HEAD. The target lifecycle
retains its actual target GITHUB_SHA. GitHub ignores reserved-variable step-env overrides.
Check the producer's archive SHA-256 independently before every consumer install. Do not confuse
the GitHub artifact-container digest, archive SHA-256, canonical archive SHA-512, or policy digest.

## Evidence and verification

Primary sources: exact workflow/scripts, Flow package builder/verifier, GitHub API state, and
[GitHub artifact documentation](https://docs.github.com/en/actions/tutorials/store-and-share-data).
Context7 independently confirms immutable v4 uploads and unique artifact naming. GitHub documents
download digest mismatches as warnings, so use a failing archive checksum check.
Independent reviewers traced credential, evidence, approval, source-identity, and job dependencies.

Budgets remain implementation 1,000,000 tokens/$2/1,800,000 ms and review 500,000 tokens/$1/1,200,000 ms.
These are settlement-accounted ceilings, not prepaid reservations. Keep all attempts in the
denominator. Hard runner termination can still leave incomplete private evidence.

## Checklist

- [x] Explore source, issue, hosted checks, approval transport, and dependency boundaries.
- [x] Compare preparation alternatives and select the artifact-first job graph.
- [x] Add regression guards and implement preparation-only changes.
- [x] Run tests, syntax checks, independent review, and untouched-base negative control.
- [ ] Commit, review, and merge preparation; freeze the exact target base (active).
- [ ] Securely provision existing credentials and verify evidence-key custody; dispatch once.
- [ ] Authenticate retained artifacts; inspect candidate, review, and check evidence before approval.
- [ ] Record the terminal result and complete denominator; remove dedicated pilot secrets.

Current status: preparation only. No model invocation or credential provisioning has occurred.

## Preparation verification

- Control regression tests: 21 passed. The original three guards failed before implementation.
  The source-identity correction also failed against the rejected step-env configuration first.
- Existing Python suite: 116 passed. Ruff, mypy (29 files), compilation, and shell syntax passed.
  Local tools use Python 3.14.6/pytest 9.1.1; hosted configuration retains Python 3.11/pytest 9.0.2.
- Independent YAML parsing verified the three-job graph. All 13 run-step shell bodies passed bash
  syntax checks. This is not a substitute for executing the GitHub workflow.
- All four frozen plan/holdout/workflow files match the prior base byte-for-byte. The unchanged
  behavioral holdout fails on the untouched target because status is absent, as required.
- Mutation checks reject missing installed-tree verification, private-file package uploads,
  missing preapproval evidence, and missing checksum enforcement. The unchanged harness passes.
- Independent security and specification/test reviews resolved a source-identity P2 and two
  regression gaps. No P1, P2, or P3 findings remain in the preparation delta.
- The local canonical package prepare and installed-package verify commands passed using the
  child-only GITHUB_SHA removal. These local bytes are not the future hosted trial artifact.
- Existing provider and evidence keys are present with owner-only permissions. The evidence key
  authenticates the first attempt's retained encrypted artifact. No key value was disclosed or
  replaced, and no Actions secret has been provisioned during preparation.

The rejected step-env design would fail during the package builder's source check, before packing.
[GitHub variable rules](https://docs.github.com/en/actions/reference/workflows-and-actions/variables)
and the runner's ScriptHandler implementation confirm why reserved step-env overrides are ignored.
