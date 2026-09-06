# Installed-package hosted pilot

This configuration qualifies the installed Flow command against issue 106. It does not implement
the issue and does not establish a supported hosted Flow service.

Current status: preparation only. Both completed hosted attempts failed before accepted
implementation. The baseline-test and assessment corrections are approved, but no further pilot
dispatch, credential provisioning, or candidate merge is authorized by that approval.

## Frozen scope

- Target: the clean `main` commit after this preparation is reviewed and merged.
- Flow source: `e967c29082a6647a1554fdc96312a93c6f94dd6d`. Prepare one canonical archive on
  Ubuntu 24.04 x64, retain it, and verify the same bytes on Ubuntu 24.04 x64 and macOS 15 Intel
  before model execution. Install those bytes into the Linux pilot's separate consumer directory.
  The manifest version is still alpha.4 and does not identify the older published alpha.4 bytes.
- Model: OpenRouter `z-ai/glm-5.3-flash`, with no fallback or route change.
- Attempt ceiling: one full lifecycle run, with only the workflow-declared bounded recovery.
- Maximum reported model cost: $2 for implementation plus $1 for review. Provider accounting is
  not a prepaid spending reservation. Each workflow also freezes token, time, output, and artifact
  limits. The smaller task gets smaller budgets than issue 6; these are pilot choices, not standards.
- Private runtime holdout: `.flow/verification/pilot-106.py`, frozen before implementation and
  excluded from model workspace access by Flow. Its source is visible to repository maintainers;
  it is not a secret benchmark dataset.
- Candidate writes: only the installer, a new focused status test file, and the installer guide.
  Workflow configuration, holdout, and existing tests cannot be edited by the model.

## Start and observe

The operator configures three dedicated Actions secrets through a secure local process:
`FLOW_PILOT_OPENROUTER_API_KEY`, `FLOW_PILOT_GH_TOKEN`, and `FLOW_PILOT_EVIDENCE_KEY`.
Reuse the existing OpenRouter key. Never put credential values in commands, issues, or logs.
The evidence key is 32 random bytes encoded as lowercase hexadecimal and retained locally with
owner-only permissions. It is not a model-provider credential.

The current repository setting disallows pull-request creation with the built-in Actions token.
This bounded pilot uses an explicitly authorized existing GitHub credential as a temporary secret.
That credential has broader scope than the target repository. This is an explicit pilot limitation,
not a recommended production identity. Prefer a repository-scoped short-lived GitHub App credential
for a supported hosted product. Remove all three dedicated secrets after evidence is retrieved.

Dispatch `flow-pilot-106.yml` from reviewed `main` as `danielbentes`. The workflow rejects other
branches, actors, and rerun attempts. It builds and installs dependencies before exposing pilot
credentials. Flow owns the sandbox, GitHub operations, verification, and durable lifecycle state.
The script only invokes the installed CLI and stops rather than choosing repairs after failure.

Before credential admission, the installed CLI runs the model-free baseline workflow. It executes
the exact plan-declared pytest command through Flow's native sandbox. A failure stops the pilot
before model spending. The check records zero model tokens and cost, retains its full output with
encrypted evidence, and prints only a content-free status. This baseline check is separate from
candidate verification and does not implement the issue.

The implementation workflow now follows `implement` → `verify-tests` → `assess`. The middle node
runs the exact frozen pytest command in the production sandbox. Nonzero or inconclusive results
stop progress before assessment. Assessment receives the implementation summary and the host's
pytest verdict and reason. It judges the implementation handoff only. It must not require receipts
from later candidate verification, private holdout, independent review, hosted CI, approval, or merge.
Those stages remain mandatory after the handoff. A summary and pytest pass are not final acceptance.

All aggregate budget ceilings remain unchanged. Three normal implementation-workflow node starts
leave one spare within the four-start ceiling. Per-node recovery limits do not override that shared
ceiling. The plan, private holdout, review workflow, provider, model, and candidate paths are unchanged.

The `prepare` job uploads only the public-source archive and its canonical release-evidence
document. The `verify` matrix uses the existing Flow package verifier and fails on an archive
checksum mismatch. The `pilot` job requires both host checks to pass, checks the producer's
SHA-256 again, and verifies its actual installed package before receiving model credentials.
No consumer repacks the archive. Package checks do not publish a GitHub release or npm version.

Package preparation and verification remove inherited `GITHUB_SHA` only from their child processes.
The package scripts then resolve the verified Flow checkout's commit. The target's Actions revision
remains unchanged for the lifecycle. GitHub ignores workflow-level overrides of its reserved
variables, so a step-level override cannot establish the package source identity.

The run summary reports phase changes and the exact approval record. At the merge gate, review the
candidate, deterministic evidence, independent review, and required checks. Only then post the exact
record on `synaptiai/flow-harness` PR 201. The pilot accepts only a new, unedited comment by immutable
GitHub user ID `158701` with the exact Actions run, Flow run, PR, head, and gate digest. It refetches
that comment before invoking the ordinary exact-head merge command. It never executes comment text.
The control comment is outside the target issue and PR so it cannot alter their frozen state.

Execution and CI waiting have a 90-minute ceiling. The separate approval step has a 30-minute
ceiling on the same runner. Missing approval means no merge.
Repository administrators and the Actions host remain trusted. This transport does not provide
multi-user authorization, a durable hosted service, or cross-host recovery.

## Retain and inspect evidence

Download `flow-pilot-106-<Actions-run-ID>-package` before its 14-day retention expires. Preserve both
the exact archive and `package-release-evidence.json` locally. Check the archive's SHA-256 against
the preparation job's recorded output. The canonical evidence also binds its SHA-512, source
revision, size, and file manifest. GitHub's artifact-container digest and Flow's installed policy
digest are different identities and must not be recorded as the package digest.

Before the approval step, the workflow archives the private run records and worktree collection.
It encrypts them with AES-256-GCM and uploads a seven-day `preapproval` artifact. Download and
authenticate this snapshot to review the exact candidate evidence before posting approval.
The final steps retain a separate `final` snapshot, including merge or failure evidence.
The file format is the nine-byte ASCII
header `FLOW106V1`, a 12-byte nonce, ciphertext, and a 16-byte authentication tag. The authenticated
additional data is `flow-pilot-106-v1`. Authenticate the complete ciphertext before consuming
decrypted data. Never upload the unencrypted archive or the key.

Download and authenticate the artifact on the operator's machine while the key remains available.
Preserve every attempted run, failed check, intervention, and available usage value. Do not restore
the archive as a runnable Flow host: it is forensic evidence, not supported host migration.

A hard runner termination can prevent the final evidence step. In that case, preserve available
GitHub observations and report missing private evidence; do not qualify the run or silently rerun it.
After any failure, record its cause and disposition before authorizing a replacement frozen attempt.

## Replacement attempt

The September 5 first attempt, Actions run `33967000922`, failed before review or publication.
It remains part of the qualification denominator. The user authorized one replacement attempt on
September 6 after the command-discovery correction. That attempt kept the plan, private holdout,
implementation and review workflows, model, and budget ceilings unchanged. The preparation merge
became its frozen base. The operator dispatched once without a rerun.

That replacement, Actions run `34021026823`, also failed before review or publication. It retained
and verified the same archive on both named hosts. Its implementation reported a failing existing
test, and assessment rejected the handoff. The marker test incorrectly searched all serialized
metadata for words that can occur in legitimate paths. The preparation correction replaces those
substring checks with exact structural assertions and adversarial path and metadata cases.

The prospective implementation workflow is now revised as described in the handoff sequence.
Historical run evidence and frozen workflow bytes remain unchanged in their retained records.
Review and merge this preparation before requesting authorization for another bounded attempt.
The target status feature must remain absent until an authorized harness run implements it.

`github.run_attempt == 1` rejects reruns of an Actions run. It does not prevent another manual
dispatch. Enforcing the single-dispatch authorization remains an operator responsibility.
