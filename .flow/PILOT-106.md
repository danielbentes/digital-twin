# Installed-package hosted pilot

This configuration qualifies the installed Flow command against issue 106. It does not implement
the issue and does not establish a supported hosted Flow service.

Current status: option B is approved for one pilot after reviewed preparation. The third attempt
passed implementation and deterministic verification, but independent review found one P3 defect.
The report validator then incorrectly rejected the valid blocked report. The prospective prompt
correction separates report validity from candidate acceptance. The new attempt adds one bounded
repair cycle. It does not reopen a historical run or authorize final candidate merge.

## Frozen scope

- Target: the clean `main` commit after this preparation is reviewed and merged.
- Flow source: `544aebc13bfc50879de52396062a869ca975c367`. All source CI jobs passed before selection.
  Prepare one canonical archive on
  Ubuntu 24.04 x64, retain it, and verify the same bytes on Ubuntu 24.04 x64 and macOS 15 Intel
  before model execution. Install those bytes into the Linux pilot's separate consumer directory.
  The manifest version is still alpha.4 and does not identify the older published alpha.4 bytes.
- Model: OpenRouter `z-ai/glm-5.3-flash`, with no fallback or route change.
- Attempt ceiling: one full lifecycle run, with at most one controller-selected repair cycle and
  the workflow-declared bounded recovery. Do not force a blocked review to exercise repair.
- Maximum aggregate reported model cost: $2 for implementation and repair together, plus $1 for
  all independent reviews. Provider accounting is not a prepaid spending reservation. The complete
  child and aggregate limits are listed in [Review the approved limits](#review-the-approved-limits).
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
The script only invokes the installed CLI. Flow selects repairs from the frozen policy and valid
blocking review evidence. The script cannot invent another repair or restart a failed lifecycle.

Before credential admission, the installed CLI validates the complete repair plan and runs the
model-free baseline workflow. It executes
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

Three normal implementation-workflow node starts leave one spare within its four-start ceiling.
Per-node recovery limits do not override a child or aggregate ceiling. The private holdout,
criteria, verification commands, provider, model, and candidate paths are unchanged.
The review validator prompt now accepts a valid blocked report as evidence while the controller
continues to block its candidate. It still rejects invalid identities, incomplete criterion
mapping, inconsistent verdicts, and unsupported evidence. An inconclusive result stops progress.
The independent reviewer, parser, and zero-findings gate remain unchanged. The child budgets are
smaller, and explicit aggregate pools account for the implementation, repair, and review children.

## Review the approved limits

The user approved option B for this pilot. These are experimental allowances, not industry
standards or a guarantee that the run finishes. One MiB is 1,048,576 bytes. Workflow costs use
US dollars; plan aggregate costs use integer microdollars, with 1,000,000 microdollars per dollar.

| Allowance | Node starts | Model tokens | Reported cost | Active milliseconds | Artifact bytes |
| --- | ---: | ---: | ---: | ---: | ---: |
| Initial implementation | 4 | 500,000 | $1.00 | 900,000 | 4,194,304 |
| Repair | 4 | 250,000 | $0.50 | 600,000 | 2,097,152 |
| Each independent review | 4 | 200,000 | $0.40 | 480,000 | 3,145,728 |
| Implementation aggregate | 10 | 1,000,000 | $2.00 | 1,800,000 | 8,388,608 |
| Review aggregate | 10 | 500,000 | $1.00 | 1,200,000 | 8,388,608 |

The implementation and repair allowances sum to eight starts, 750,000 tokens, $1.50, 1,500,000
active milliseconds, and 6 MiB. Two reviews sum to eight starts, 400,000 tokens, $0.80, 960,000
active milliseconds, and 6 MiB. Each sum fits its role's pool. The ten-start aggregate ceilings
are explicit new limits, not unchanged historical four-start child limits.

Flow requires the next child's complete allowance to fit every remaining dimension before
dispatch. Unknown usage, exhausted resources, disputed findings, unchanged or repeated trees,
and uncertain effects stop further work. Unused review capacity cannot fund implementation.
An actual usage overrun remains recorded rather than being clamped to the allowance.

The repair workflow returns either `changed` or `disputed`, bound to the exact host-supplied
context and candidate. Its validator checks the disposition, not candidate acceptance. A valid
dispute reaches the host even if a partial repair has failing tests. A changed candidate must pass
the original holdout, all five deterministic commands, and a fresh independent review. No finding
is waived or downgraded by the repair workflow.

Repair can disclose the selected review findings and original criterion evidence to the same
approved OpenRouter route. It does not disclose private holdout source, raw sessions, or credentials.

## Verify the package and approve the candidate

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
ceiling on the same runner. The job ceiling is 180 minutes. Missing approval means no merge.
These are early-stop controls, not a promise that every configured maximum fits. One full host
verification pass has 17 minutes of command timeouts. A one-repair path has four such passes before
publication, one publication gate pass, and a fresh pass after approval. Together with the
41-minute sum of child active-time limits, their configured subtotals reach 109 minutes before
publication, 126 before approval, and 143 across both phases. These are not runtime forecasts.
Each CI-wait resume can add another verification pass. Status inspection does not. Setup, check
waiting, human response, and other host work add time. Do not extend a deadline after a stop.
Repository administrators and the Actions host remain trusted. This transport does not provide
multi-user authorization, a durable hosted service, or cross-host recovery.

## Retain and inspect evidence

Download `flow-pilot-106-<Actions-run-ID>-package` before its 14-day retention expires. Preserve both
the exact archive and `package-release-evidence.json` locally. Check the archive's SHA-256 against
the preparation job's recorded output. The canonical evidence also binds its SHA-512, source
revision, size, and file manifest. GitHub's artifact-container digest and Flow's installed policy
digest are different identities and must not be recorded as the package digest.

Before the approval step, the workflow archives the private run records and this target's owned
worktrees. Retain parent dispatch and settlement records, every implementation, repair, and review
child ledger, private issue and workflow blobs, and frozen review context blobs. The review result
is recorded in the independent-review child ledger. The repair child's stored control graph
includes its bound model-verifier prompt and repair context. Repair context can also be reconstructed
from the frozen manifest, issue snapshot, review result, and selected cycle identities, then checked
against its recorded digest. Do not expect a separate repair-context blob. Retain the candidate
files without Git metadata or dependency directories.
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

The implementation correction was merged before the separately authorized third attempt,
[Actions run 34036328861](https://github.com/danielbentes/digital-twin/actions/runs/34036328861).
Both package host checks passed. The candidate passed all five checks and the private holdout,
including its negative control. Independent review reported the P3 finding
`status-docstring-dropped-subject`. The model validator rejected the report because that finding
existed, and the parent stopped as `review_workflow_failed`. No candidate PR or merge followed.
The three dedicated Actions secrets were removed after authenticated evidence retrieval.

The prospective review-prompt correction does not repair the candidate or reopen that terminal
run. Static prompt-contract tests failed before the correction and pass afterward. The local
checks pass 27 workflow-control tests and 124 Python tests, linting, and type checking. These
checks establish preparation integrity, not future model compliance or end-to-end qualification.
Historical run evidence and frozen workflow bytes remain unchanged in their retained records.
The user subsequently authorized option B. Review and merge its preparation before the one new
dispatch. The earlier check counts describe the report-validator correction, not this preparation.
The target status feature must remain absent until an authorized harness run implements it.

`github.run_attempt == 1` rejects reruns of an Actions run. It does not prevent another manual
dispatch. Enforcing the single-dispatch authorization remains an operator responsibility.
