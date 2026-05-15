# Changelog

All notable changes to the digital-twin plugin will be documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
