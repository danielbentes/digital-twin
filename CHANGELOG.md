# Changelog

All notable changes to the digital-twin plugin will be documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
- Synthesizer dumps the full agent reports into per-section placeholders rather than extracting per-section recommendations. Targeted v0.2.
