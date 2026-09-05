# Installed-package hosted pilot

This configuration qualifies the installed Flow command against issue 106. It does not implement
the issue and does not establish a supported hosted Flow service.

## Frozen scope

- Target: the clean `main` commit after this preparation is reviewed and merged.
- Flow source: `50e5e4c5c21bd1518ff6445a8cc3f93f5a93132e`. Build and pack on Ubuntu 24.04 x64,
  then install into a separate consumer directory. Record the archive digest; the manifest version
  is still alpha.4 and does not identify the older published alpha.4 bytes.
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
