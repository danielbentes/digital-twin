# Issue 106 baseline and assessment preparation

Date: 2026-09-06. Branch: `codex/pilot-106-evidence-preparation`.
Starting base: `7414509caa0c31180852c614c54f73670143a49b`.

## Authorization and scope

The user approved correcting the baseline assertion and adding stage-specific assessment with
host-produced test evidence. No new pilot dispatch, model invocation, budget increase, merge,
release, or credential provisioning is authorized by this preparation. Issue 106 remains a fresh
implementation task. Do not implement status manually or reuse a failed attempt's candidate.

The previous two failed attempts and their frozen bytes remain historical evidence. The prospective
implementation workflow and model-free baseline admission change. Keep plan, private holdout, review workflow, model,
candidate write authority, recovery settings, and aggregate budgets unchanged.

## Plan and verification map

- [x] Correct the marker test structurally, with path regressions and negative mutation controls.
  Observe failures first. Then run focused and full pytest, Ruff, mypy, compilation, and shell checks.
- [x] Add the exact frozen pytest command as a verifier after implementation and before assessment.
  Give assessment its host-produced verdict and reason. Make later lifecycle proofs explicitly
  pending. Add control regressions and verify production workflow admission, including denial of
  changed command arguments or timeout. Keep three normal node starts within the existing four.
- [x] Run the corrected untouched baseline through Flow's real sandbox without any model or secrets.
  Verify status remains absent with the unchanged negative holdout. Docker, if used locally, is
  supplementary verification and not a replacement for hosted Linux qualification.
- [x] Update the preparation guide and Flow tracking documents without rewriting failed evidence.
- [x] Complete independent code/test review and quality gates, then commit and publish preparation
  for review. Keep merge and any new pilot behind separate explicit approval.

## Design

Use existing production command-verifier semantics, not a new executor or looser command matching.
The new node uses `python3`, `[-m, pytest]`, and 300000 milliseconds exactly as declared in the plan.
Nonzero test exit rejects the node before assessment. The later controller-owned committed-candidate
verification remains authoritative and still repeats all five plan checks and the private holdout.
The model assessment can judge only the implementation handoff and declared evidence. It must not
invent missing downstream receipts or infer complete issue acceptance from a pytest pass.

## Capability discovery

Target checks are defined in `.github/workflows/ci.yml`: Python compilation, Ruff, mypy, shell syntax,
pytest, and Node's built-in test runner for pilot controls. Flow supplies production validation and
native sandbox execution. Node, Python, pytest, Ruff, mypy, GitHub CLI, and Docker are available.
No LSP tool is available, so use source navigation plus compiler and test checks. A separate agent
owns only the marker-test file while the coordinator owns workflow wiring and documentation.

## Verification evidence

- RED: ordinary marker paths passed. Paths containing command, pushback-detector, or
  pushback-detector.py failed old substring or recursive-reference assertions.
- GREEN: 33 installer tests pass, including four path variants and five negative structural controls.
  Removing the exact structural assertion in memory made all five negative controls fail.
- Full local target checks: 124 pytest tests pass; Ruff, mypy (29 files), compilation, and shell syntax pass.
- The control suite passes 25 Node tests. New handoff and baseline-order tests failed before their changes.
- Production CLI plan/workflow validation and issue workflow admission pass. Production admission
  rejects changed pytest arguments and a 299999-millisecond timeout.
- Independent YAML parsing and bash syntax checks pass for all 14 hosted run-step bodies. The
  model-free baseline command exactly matches the plan's pytest command.
- A real native Flow command-verifier run passes 123 tests with one environment-dependent skip,
  zero model tokens, and zero model cost. It uses SRT 0.0.70 and the same sandbox policy digest as
  the failed hosted run. This observation is local macOS, not hosted Linux execution of the new gate.
- The unchanged private holdout fails on absent status as expected. Installer SHA-256 remains
  7a8084ad0e4ef00f12a02bc98b2172f62a6bac0943882b3c4a53035d610c24aa.
- Revised implementation source SHA-256:
  8894491c8a9d0b7f7c8dd87799826484e60c210766de4db5433fade1a29cd53d.
  Plan, holdout, and review source digests remain unchanged.

## Limitations and negative cases

No model assessed the revised rubric. No new hosted lifecycle run, candidate implementation,
holdout pass, independent candidate review, or merge was tested. The next hosted attempt remains
separately gated. The model assessment receives an exit-derived pytest verdict/reason and the
implementation summary, not raw command output or an independently reviewed diff. This is a handoff
gate only. Three normal starts leave one spare shared across the existing recovery settings.

The hosted baseline gate now runs after installed-package verification and before the first pilot
secret. It retains full output with encrypted evidence and exposes only a content-free status.
The source-level guard requires success and zero model usage. It does not authorize dispatch.

## Review and classification

All seven target changes are in scope: the marker test, two preparation workflows, hosted gate,
control tests, operating guide, and this journal. No application implementation or original plan,
holdout, or review workflow changed. Independent review found no remaining P1–P3 code findings.
A historical imperative in the guide was corrected to past tense and re-reviewed without findings.
Flow's four tracking documents pass style, links, clarity, and whitespace checks and independent review.
Preparation commit `cd2a5a5` was pushed and [PR 109](https://github.com/danielbentes/digital-twin/pull/109)
was opened for review. Its body uses a non-closing related-issue reference. Hosted PR checks remain
a merge prerequisite. Merge and dispatch remain separate approvals. The baseline and handoff
checks have not been run as a new hosted lifecycle attempt.
