---
name: digital-twin
description: |
  Mine the user's own Claude Code session logs to build a behavioral profile
  and an installable subagent that mirrors how they actually orchestrate Claude
  Code. Produces a personalized PROFILE.md (+PROFILE.html with charts), a
  twin.md subagent, a CLAUDE.md patch, a per-user gotchas catalog, and a
  canonical numbers source-of-truth — all from local jsonl logs. Local pipeline
  runs in ~20 seconds on a 10k-session corpus; the three LLM-bound phases
  (deep-read agents, profile extraction, and
  behavioral-spec extraction) dominate wall-clock.

  Use when the user says any of: "build a digital twin of me", "make a personal
  agent from my prompts", "analyze my Claude Code usage", "mine my session
  logs", "I want a twin agent", "build an agent that acts like me", "encode my
  workflow as a subagent", "create a personalized orchestrator", "build a
  CLAUDE.md from my history", "what does my Claude Code usage look like",
  "show me my prompt patterns".

  This skill MUST be consulted for those requests because no other skill or
  generic agent can produce a personalized orchestrator from log mining —
  generic best-practice agents won't capture the user's specific conventions,
  vocabulary, project glossary, pushback triggers, or recovery cycles. Even if
  the user phrases the request indirectly ("analyze my workflow", "build a
  CLAUDE.md for me", "what's my style?") consult this skill — the output is
  materially different from a generic agent because it quotes the user's
  actual prompts, encodes their actual memory rules, and matches their actual
  voice.
---

# Digital Twin

Build a personalized Claude Code subagent from the user's own session logs.

## What this skill produces

| Artifact | Path | Purpose |
|---|---|---|
| Profile (md) | `~/.claude/digital-twin/PROFILE.md` | Behavioral analysis with ASCII charts |
| Profile (html) | `~/.claude/digital-twin/PROFILE.html` | Same content, inline SVG charts, self-contained |
| Subagent | `~/.claude/agents/twin.md` | Installable orchestrator |
| CLAUDE.md patch | `~/.claude/digital-twin/CLAUDE-md-patch.md` | Global defaults addendum |
| CLAUDE rules | `~/.claude/digital-twin/rules/*.md` | Compact installable preference/workflow/verification/recovery rules |
| Gotchas card | `~/.claude/digital-twin/gotchas.md` | Per-user gotchas catalog |
| Canonical numbers | `~/.claude/digital-twin/numbers.md` | Verification source-of-truth |
| Raw corpora | `~/.claude/digital-twin/corpora/*.jsonl` | For re-analysis |

## When to use this skill

- User asks for a "digital twin" / "personal agent" / "subagent that acts like me"
- User says "analyze my Claude Code usage" or "mine my prompt logs"
- User wants to install a CLAUDE.md or subagent based on observed behavior
- User invokes `/digital-twin:init`, `/digital-twin:update`, `/digital-twin:status`, or `/digital-twin:propose-rules`

## When NOT to use this skill

- User has fewer than ~500 prompts in their corpus — insufficient signal. Run `scripts/extract-corpus.py --count-only` to verify and warn.
- User wants a generic best-practice agent — point them at standard Claude Code skills.
- User is on a shared machine and might not be the original prompt author — confirm identity before proceeding.

## Workflow overview

The full methodology lives in `references/methodology.md` — read it before driving a run. The summary:

| Phase | Wall-clock (measured) | What runs |
|---|---|---|
| 1. Setup | seconds | Confirm `~/.claude/projects/` exists, count files, confirm identity, ask for UTC offset |
| 2. Extract | ~5 sec / 10k sessions | `scripts/extract-corpus.py` |
| 3. Quantitative | ~10 sec | `scripts/quantitative.py` (~8 s), `scripts/temporal.py` (~1 s) — run in parallel |
| 4. Deep sources | ~5 sec | `memory-inventory.py`, `plan-inventory.py`, `assistant-turn-mining.py`, optional `pr-comment-mining.sh` — all local, run in parallel before the LLM reports |
| 5. Qualitative agents | LLM-bound, varies | 6 `general-purpose` agents in parallel writing free-form Markdown deep reads to `analysis/reports/`. Wall-clock depends on model latency and parallel-dispatch overhead. |
| 5.5. Insights extraction | 3-10+ min | Single Sonnet call (~180 KB input) distills the 6 reports + stats into 7 structured JSON files. Hard timeout at 15 min; falls back to Tier 2 if it overruns. |
| 5.6. Twin spec extraction | 3-10+ min | Single Sonnet call distills reports + insights + stats + deep-source inventories into `analysis/twin-spec.json`, the source of truth for the replacement agent |
| 6. Synthesize | <1 sec | `scripts/synthesize.py` produces PROFILE.md + PROFILE.html (card-styled) + compact twin.md + CLAUDE.md patch + generated rule files |

**Local pipeline total (Phases 2, 3, 4, 6): ~20 seconds on a 10k-session corpus.** The LLM-bound phases (5, 5.5, and 5.6) dominate wall-clock; their cost is the cost of the whole run.

**Three-tier robustness in synthesize.py**: if Phase 5.5 insights JSON is present, profile cards render from rich agent-derived content (Tier 1). If only Phase 5 reports exist, cards fall back to rule-based content scraped from numbers + reports (Tier 2). If Phase 5 was skipped entirely, sections show `_pending_` markers but the profile still completes (Tier 3). The replacement agent is stricter: if `analysis/twin-spec.json` is missing or invalid, `twin.md` is generated with an explicit incomplete-spec warning.

The `/digital-twin:init` slash command orchestrates all six phases — prefer it over running scripts manually. See `commands/init.md` for the exact orchestration sequence.

## Phase 5 dispatch — the only non-trivial step

Phases 2, 3, 4, and 6 are pure script invocations. Phase 5 is different: you (the model) dispatch 6 `general-purpose` subagents in **one message**, each filled in from a template at `references/prompts/`:

1. `orchestration-deep-read.md` — how the user delegates
2. `workflow-deep-read.md` — issue → plan → impl → verify → ship lifecycle
3. `quality-deep-read.md` — pushback, conventions, voice
4. `encoded-rules-deep-read.md` — memory rule survey
5. `planning-style-deep-read.md` — plan archetypes
6. `failure-recovery-deep-read.md` — convergence pairs

Each prompt has `{{USER_NAME}}`, `{{PROMPT_COUNT}}`, `{{CORPUS_PATH}}`, etc. placeholders. Fill them from `numbers.json` (produced in Phase 3) and the deep-source outputs (produced in Phase 4) before dispatch. Save each agent's report to `~/.claude/digital-twin/analysis/reports/<angle>.md` so the synthesizer in Phase 6 can pick them up.

If Phase 5 is skipped, `synthesize.py` still produces a working profile — the per-angle sections render as `_pending_` and the synthesizer's own narrative builders fill the headline / what-works / friction / suggestions sections from the quantitative data alone.

## Slash commands

| Command | Purpose |
|---|---|
| `/digital-twin:init` | Full first-time run (Phases 1-6) |
| `/digital-twin:update` | Re-run Phases 2-6 against newer logs |
| `/digital-twin:status` | Show last-run state + drift since |
| `/digital-twin:propose-rules` | Review pushback-detected rule proposals |

## Privacy guarantees

- **Local phases stay local.** Corpus extraction, quantitative passes, memory/plan/convergence inventories, and final rendering run as local scripts reading from `~/.claude/projects/`.
- **LLM phases send corpus-derived evidence to Claude:** (a) Phase 5 dispatches 6 deep-read agents via the Agent tool, (b) Phase 5.5 makes one profile-insights extraction call via `claude -p`, and (c) Phase 5.6 makes one behavioral-spec extraction call via `claude -p`. All ride the same auth you already use; no Anthropic API key required unless `extract-insights.py --allow-sdk-fallback` is explicitly enabled.
- **Optional `gh api`** for PR comment mining only — skipped gracefully if `gh` isn't authenticated.
- **No plugin telemetry.** The skill does not phone home outside the explicit Claude/GitHub calls above.
- **No auto-memory writes.** Every rule proposal requires explicit approval via `/digital-twin:propose-rules`.
- **No auto-CLAUDE.md edits.** The patch lands as a separate file the user copies.

## Cost model

API spend is from three Sonnet-backed LLM steps:

- **Phase 5 (deep-read agents)**: 6 agents × ~80k input + ~12k output ≈ 540k tokens. Sonnet pricing puts this at ~$4-8 per first run. Skipped on `update` when cached reports are reused.
- **Phase 5.5 (profile extraction)**: one ~180 KB input + ~10 KB output ≈ 50k tokens, ~$0.50-1.
- **Phase 5.6 (twin spec extraction)**: one similar-sized input + compact JSON output, ~$0.50-1.

**First run total**: ~$5-9. **Update without re-running agents**: ~$1. **Pushback detector** (per-turn, if hooked): essentially free (filesystem scan only).

These are upper-bound estimates from Sonnet pricing on the v0.1 corpus shape. Lighter corpora (~5k prompts) cost proportionally less.

## Critical guardrails inherited by the synthesized twin

- NEVER commit without explicit user approval.
- NEVER force-push to main/master.
- NEVER auto-write to memory files without `/digital-twin:propose-rules` review.
- NEVER claim a finding without quoting corpus evidence.
- NEVER omit a section if no evidence is found — leave it explicitly empty with a `_no evidence_` marker.

## Roadmap

See `references/methodology.md` § "Roadmap". Next: per-section recommendation extraction from deep-read reports (v0.2), Cursor adapter (v0.3), marketplace publication (v0.4).
