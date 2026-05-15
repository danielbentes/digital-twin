# Changelog

All notable changes to the digital-twin plugin will be documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.4.0] — 2026-05-15

### Added
- **Substitution contract.** New first-class spec sections — `constitution`, `substitution_contract`, `trust_policy`, `agent_supervision_policy` — rendered into `twin.md`, the new `rules/substitution.md` output, and the CLAUDE.md patch. The generated twin now represents the user's operating principles, authority boundaries, trust behavior, and agent-supervision stance, not just always/never rules.
- **Principle-rich durable rules.** `never_rules` / `always_rules` schema items add `principle`, `because`, `applies_when`, `failure_mode`, `example_good`, `example_bad` so judgment transfers to held-out situations. Renderer emits these fields when present and degrades gracefully when extraction omits them.
- **`--strict-substitution` flag** in `synthesize.py`. When set, a legacy v1 spec missing the four substitution sections emits a degraded twin instead of compatibility-derived authority — closes the silent-inheritance gap from v0.3.0.
- **`--strict-substitution`-gated compatibility path.** Legacy specs without substitution sections are backfilled via `_legacy_substitution_fields` with prose `because` reasons (citation paths stay in `evidence`), filtered through a destructive-verb deny-list so legacy `decide_alone` entries naming force-push / publish / release / delete / drop / truncate / deploy-to-prod / merge-to-main never become autonomous authority. Renderer surfaces `compatibility-derived substitution defaults` status banner.
- **`sanitize_user_name`.** `--user-name` is normalized at parse time: control chars stripped, length capped at 64, allow-listed to `[A-Za-z0-9 ._-]`. Replaces ad-hoc HTML escaping of user_name with a stronger upstream sanitization.
- **Pushback proposal scaffolds.** `pushback-detector.py` proposals now include `Underlying principle`, `Rationale`, `Applies when`, `Does not apply when`, `Failure mode`, `Trust/delegation implication` sections. New `proposal_ready_for_approval(body)` helper detects unfilled `_Fill in_` placeholders so the approval guard in `/digital-twin:propose-rules` is testable.
- **`SOUNDS_APPROVAL_RE`.** Two-token approval detection for `sounds (good|right|fine|great|reasonable|like a plan)` — `"sounds bad"` / `"sounds wrong"` no longer misclassify as approval.
- **Eval harness coverage.** `score_response` adds `concept_coverage` and `forbidden_match` axes. `evaluate` reports `pushback_trigger_avoidance_rate` separately from `pushback_trigger_hit_rate`. `category_scores` averages per-case ratios so cases with optional checks no longer dilute thinner cases in the same category.
- **Held-out eval fixtures.** 9 multi-agent / supervision / authority / trust scenarios under `tests/fixtures/eval/heldout_cases.json`, including authority-boundary, agent-disagreement-consolidation, review-agent-plan-overbroad, agent-brief-nontrivial, and delegation-parallel cases.
- **17 new tests.** Negative coverage for non-dict legacy spec sections, destructive-verb deny-list, prose-vs-citation `because`, partial-population compat detection, corrupt state-file recovery, user_name sanitization, strict-substitution flag, scaffold-guard parser, per-case-ratio normalization, missing mock-response file, slug content-hash suffix, `sounds bad` not approval.

### Changed
- **`normalize_twin_spec_for_rendering`** now `copy.deepcopy()` inputs so callers retaining the original spec do not see backfilled keys mutated in. Type-guards each section with `_safe_dict` before reading, so non-dict legacy values (`"TBD"`, lists, ints) no longer crash the renderer.
- **`needs_compatibility_defaults`** helper centralizes the legacy detection logic and treats present-but-non-dict sections as needing backfill.
- **`evaluate-twin.py:score_response`** documents the `avoid_phrases` (trigger-coupled) vs `forbidden_phrases` (universal) split.
- **`twin-spec-schema.json`** adds 4 required policy sections, expands rule schemas with principle/rationale/applicability fields, and tightens `minItems` constraints on substitution arrays.

### Fixed
- **Mypy CI failure.** `detail_fields` in `render_rule_block` is now annotated as `tuple[tuple[str, str], ...]` so variable-length assignments type-check (`synthesize.py:2185-2191`).
- **State-file robustness in `pushback-detector.py`.** Non-dict / corrupt JSON state files emit a stderr WARN and rescan from scratch instead of crashing on `state.setdefault(...)`. Inner `offsets` / `seen_hashes` are also type-guarded.
- **`load_text` / `load_json`** in `extract-twin-spec.py` now print stderr WARN with the failing path on `OSError` / `JSONDecodeError` instead of silently returning empty defaults. `build_stats_packet` rejects non-dict analysis JSON before mutating.
- **`--mock-response-file`** in `extract-twin-spec.py` reports `ERROR: --mock-response-file path not found: {path}` before any JSON parsing, replacing the previous generic "twin spec response was not valid JSON".
- **`load_schema`** error messages include the schema path (`twin_spec_validation.py`).
- **Session-file scan in `pushback-detector.py`.** `WARN: could not stat / open {fpath}` instead of silent skip; corrupt JSONL lines counted and reported.
- **Proposal slug collisions.** Proposal `name:` carries an 8-char content-hash suffix; empty replies are skipped before reaching `proposal_body`.
- **Heldout fixture `agent-disagreement-consolidation`.** Removed `"majority"` from a concept group that also listed it as forbidden, eliminating a trap where the expected behavior contradicted itself.
- **`because` vs `evidence` swap.** Legacy backfill no longer writes citation strings (e.g., `"quality.md §6"`) into the `because` field — `because` carries prose reasons; citations stay in `evidence`.

### Security
- Destructive-verb deny-list filter on legacy `decide_alone` items prevents force-push / publish / release / delete / drop / truncate / deploy-to-prod entries from silently becoming autonomous authority on compatibility-backfilled twins.
- `sanitize_user_name` allow-list prevents user_name injection into rendered markdown/HTML (newlines, tags, control sequences). XSS test updated to assert the stronger upstream defense.
- `--strict-substitution` lets operators refuse legacy authority backfill entirely.

### Validation
- 49 tests passing (was 32 before this release).
- mypy, ruff, `python -m compileall`, shell `bash -n`, and the CI workflow all green.
- Eval harness on held-out fixtures: `n=9`, `twin_win_rate=1.0`, `pushback_trigger_hit_rate=1.0`, `pushback_trigger_avoidance_rate=1.0`, all 8 category scores at 1.0.

## [0.3.0] — 2026-05-15

### Added
- **Behavioral Twin v1.** Added a dedicated `analysis/twin-spec.json` extraction phase and schema. `twin.md` is now rendered from a compact operational behavior contract instead of a profile summary or raw memory dump.
- **Generated CLAUDE rules.** Synthesis now writes `rules/preferences.md`, `rules/workflows.md`, `rules/verification.md`, and `rules/recovery.md`; `CLAUDE-md-patch.md` is a short install guide that imports those files.
- **Deterministic eval harness.** Added held-out behavior fixtures and `scripts/evaluate-twin.py` to compare the generated twin against a generic baseline without live LLM calls.
- **CI.** Added GitHub Actions coverage for Python compile checks, Ruff, mypy, shell syntax, and pytest.

### Changed
- **Corpus signal extraction.** Full `user`/`human` messages now beat duplicate truncated `last-prompt` rows, while unmatched `last-prompt` rows remain available as evidence. Corpus records now include `source_type`, `is_auto_wake`, and `is_human_typed`.
- **Profile generation.** `synthesize.py` uses `twin-spec.json` for agent output, validates nested spec structure, and emits an explicit incomplete-spec warning if the behavioral contract is missing or invalid.
- **Manual pipeline.** README and command docs now run twin-spec extraction by default for replacement-agent output, with `--allow-empty` reserved for local-only degraded fallback paths.
- **LLM timeout control.** `extract-insights.py` now accepts `--timeout`; real-corpus validation required a longer timeout than the previous 900-second default.

### Fixed
- **Real-data validation artifact issue.** `PROFILE.md`/`PROFILE.html` now fall back to `corpora/_summary.json` for session-file counts when `numbers.json` does not include them, avoiding `Sessions ?` in fresh manual runs.
- **Slash command metrics.** Path/API fragments such as `/api`, `/users`, `/tmp`, and `/month` no longer count as slash workflows.
- **Spec rendering.** Normalizes model-supplied bullet/number prefixes before rendering numbered lists, avoiding artifacts like `1. 1. Detect`.

### Security
- Sanitizes LLM-provided profile HTML fragments and escapes scalar placeholders before rendering `PROFILE.html`.
- Removes external font requests from generated/sample HTML.
- Escapes SVG chart text and aria labels.
- Treats corpus text, reports, memory bodies, paths, and quotes as untrusted evidence in all extraction/deep-read prompts.
- Makes Anthropic SDK/API-key fallback opt-in via `--allow-sdk-fallback`.
- Removes `WebFetch` from the default generated twin subagent tool list.
- Skips symlinked or out-of-source session/memory files during corpus extraction, assistant-turn mining, memory inventory, and pushback detection.

### Validation
- Ran the release pipeline on Daniel's real corpus: 9,678 prompts, 1,140 session files, 144 memory files, 27 plans, 3,550 assistant/user convergence pairs, Tier 1 insights, and a complete schema-valid `twin-spec.json`.

## [0.2.0] — 2026-05-12

### Added
- **Phase 4.5 — Insights extraction pass.** New `scripts/extract-insights.py` runs a single Sonnet 4.6 call that reads the 6 free-form deep-read reports + corpus stats and emits 7 structured JSON files (`project_areas`, `interaction_style`, `big_wins`, `friction`, `suggestions`, `horizon`, `fun_ending`) matching `references/insights-schema.json`. Auto-repair for common LLM bracket mistakes (e.g., spurious `}` before `"horizon"`). 15-min hard timeout.
- **Three-tier card sourcing in `synthesize.py`.** Tier 1 (insights JSON present) → render cards directly from JSON with `source` citations. Tier 2 (reports only) → rule-based card builders that scrape reports for bullets. Tier 3 (neither) → `_pending_` markers, pipeline never hard-fails.
- **Encoded-rules cards.** Each memory rule is now parsed by `**Label:**` markers into Rule / Why / How-to-apply sections and rendered as a structured card. Cards grouped by project in collapsible `<details>` blocks. Quoted user pushbacks in descriptions are peeled out and rendered as amber blockquotes.
- **Polished SVG charts.** Hour-of-day switched from heatmap to vertical bar chart with peak-hour highlight and working-hours band. Day histogram adds share % above each bar and italicizes the peak day. Convergence donut redesigned: bigger (540×340), in-segment % labels, larger legend with bold counts.
- **`agents/twin-placeholder.md`** — stub sub-agent installed before first `/digital-twin:init` run, with honest "I'm the placeholder twin" response.
- **8 new tests in `tests/test_insights.py`** covering schema validation, renderer-consumes-JSON, Tier 1 / Tier 2 / Tier 3 paths, mock extraction, invalid-JSON handling, empty-reports fallback, and a Daniel-specific content gate.

### Changed
- **Privacy claims corrected** across `plugin.json`, `SKILL.md`, `README.md`, and `commands/init.md`. The previous "entirely offline / no network calls" language was inaccurate — Phase 4 dispatches 6 LLM agents and Phase 4.5 makes one Sonnet call. New language: "Your session logs never leave your machine. Two LLM steps use your existing Claude Code auth."
- **Time/cost claims replaced with measured numbers.** Local pipeline (Phases 2, 3, 5, 6) measured at ~20 seconds on a 10k-session corpus. LLM-bound phases (4 and 4.5) are now honestly described as variable rather than quoted as fixed minutes. Cost remains ~$5-9 first run / ~$1 update.
- **`commands/init.md`** updated with explicit Phase 4 dispatch sequence (6 parallel Agent calls) and Phase 4.5 step.
- **`SKILL.md`** workflow table now shows measured times for local phases and "LLM-bound, varies" for Phases 4 and 4.5.
- **`profile-template.md`** restructured to mirror `PROFILE.html`'s card sections; deep-read text dumps removed.

### Fixed
- **v0.1.0 known limitation resolved**: "Synthesizer dumps the full agent reports into per-section placeholders rather than extracting per-section recommendations" — this is now Phase 4.5's job.
- **Python 3.11 compatibility**: f-string with escaped quotes inside expression part (only allowed in 3.12+) extracted to a local variable.
- **5 orphan ctx keys removed** from `synthesize.py` after the v0.2 template restructure: `ENCODED_RULES_SECTION_HTML` (replaced by `_CARDS_HTML`), `STAT_CARDS_SVG`, `IDENTITY_SECTION_HTML`, `PROJECT_GLOSSARY_HTML`, `DRIFT_SUMMARY`.
- **`extract-insights.py` timeout** bumped from 10 to 15 min after observing real-corpus runs that hit the cap.

### Distribution
- Added `.claude-plugin/marketplace.json` so the repo is also a single-plugin marketplace. Users can now `/plugin marketplace add danielbentes/digital-twin` and `/plugin install digital-twin@digital-twin`.

## [0.1.0] — 2026-05-11

### Added
- Initial public release as a Claude Code plugin.
- Six-pass synthesis pipeline (`extract-corpus.py`, `quantitative.py`, `temporal.py`, `memory-inventory.py`, `plan-inventory.py`, `assistant-turn-mining.py`, `synthesize.py`).
- Pushback detector (`pushback-detector.py`) — incremental, stateful, never auto-writes.
- Four slash commands: `/digital-twin:init`, `/digital-twin:update`, `/digital-twin:status`, `/digital-twin:propose-rules`.
- Profile output in both Markdown (with ASCII charts) and HTML (with inline SVG charts).
- Insights-style narrative sections: project areas, what-works, friction patterns, suggestions, on-the-horizon, fun-finding.
- Generated artifacts: `PROFILE.md`, `PROFILE.html`, `twin.md` sub-agent, `CLAUDE-md-patch.md`, `gotchas.md`, `numbers.md`.
- Auto-detection of dominant non-English language (EN/NO/DE/ES/FR).
- Plan archetype detection (surgical vs multi-phase) and out-of-scope drift signal.
- 6 qualitative deep-read agent prompts orchestrated by `/digital-twin:init`.
- Synthetic-corpus test in `tests/`.

### Privacy guarantees
- No network calls in any script.
- No telemetry.
- No auto-writes to memory — every rule approval is explicit.

### Known limitations
- Implicit-pushback heuristic has a ~15% false-positive rate on tested corpora; tune with `--min-confidence`.
- Plan-inventory's default scan only covers `~/.claude/plans/` and `~/.claude/projects/*/.decisions/` — pass `--search-dir` for additional locations.
- Synthesizer dumps the full agent reports into per-section placeholders rather than extracting per-section recommendations. _(Resolved in unreleased v0.2 — see `[Unreleased]` above.)_
