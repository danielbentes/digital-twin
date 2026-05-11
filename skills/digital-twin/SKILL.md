---
name: digital-twin
description: |
  Mine the user's own Claude Code session logs to build a behavioral profile
  and an installable subagent that mirrors how they actually orchestrate Claude
  Code. Produces a personalized PROFILE.md (+PROFILE.html with charts), a
  twin.md subagent, a CLAUDE.md patch, a per-user gotchas catalog, and a
  canonical numbers source-of-truth — all from local jsonl logs in ~60-90 minutes.

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

| Phase | Wall-clock | What runs |
|---|---|---|
| 1. Setup | ~2 min | Confirm `~/.claude/projects/` exists, count files, confirm identity, ask for UTC offset |
| 2. Extract | ~3 min | `scripts/extract-corpus.py` |
| 3. Quantitative | ~3 min | `scripts/quantitative.py`, `scripts/temporal.py` (parallel) |
| 4. Qualitative agents | ~20 min | 6 `general-purpose` agents in parallel — see `references/prompts/` |
| 5. Deep sources | ~15 min | `memory-inventory.py`, `plan-inventory.py`, `assistant-turn-mining.py`, optional `pr-comment-mining.sh` (parallel) |
| 6. Synthesize | ~10 min | `scripts/synthesize.py` produces all final artifacts |

**Total: ~60-90 minutes** on a typical 5k-15k prompt corpus.

The `/digital-twin:init` slash command orchestrates all six phases — prefer it over running scripts manually. See `commands/init.md` for the exact orchestration sequence.

## Phase 4 dispatch — the only non-trivial step

Phases 2, 3, 5, and 6 are pure script invocations. Phase 4 is different: you (the model) dispatch 6 `general-purpose` subagents in **one message**, each filled in from a template at `references/prompts/`:

1. `orchestration-deep-read.md` — how the user delegates
2. `workflow-deep-read.md` — issue → plan → impl → verify → ship lifecycle
3. `quality-deep-read.md` — pushback, conventions, voice
4. `encoded-rules-deep-read.md` — memory rule survey
5. `planning-style-deep-read.md` — plan archetypes
6. `failure-recovery-deep-read.md` — convergence pairs

Each prompt has `{{USER_NAME}}`, `{{PROMPT_COUNT}}`, `{{CORPUS_PATH}}`, etc. placeholders. Fill them from `numbers.json` (produced in Phase 3) before dispatch. Save each agent's report to `~/.claude/digital-twin/analysis/reports/<angle>.md` so the synthesizer in Phase 6 can pick them up.

If Phase 4 is skipped, `synthesize.py` still produces a working profile — the per-angle sections render as `_pending_` and the synthesizer's own narrative builders fill the headline / what-works / friction / suggestions sections from the quantitative data alone.

## Slash commands

| Command | Purpose |
|---|---|
| `/digital-twin:init` | Full first-time run (Phases 1-6) |
| `/digital-twin:update` | Re-run Phases 2-6 against newer logs |
| `/digital-twin:status` | Show last-run state + drift since |
| `/digital-twin:propose-rules` | Review pushback-detected rule proposals |

## Privacy guarantees

- **No network calls** during analysis (optional `gh api` for PR mining only).
- **No telemetry** — the skill does not phone home.
- **No auto-memory writes** — every rule proposal requires explicit approval.
- **No auto-CLAUDE.md edits** — the patch lands as a separate file the user copies.

## Cost model

- First run: ~6 agents × ~80k input + ~12k output ≈ 540k tokens. Sonnet: $4-8. Opus: $8-15.
- Update run: ~30% of first-run cost if deep-read agents skip.
- Pushback-detector (per-turn): essentially free (filesystem scan only).

## Critical guardrails inherited by the synthesized twin

- NEVER commit without explicit user approval.
- NEVER force-push to main/master.
- NEVER auto-write to memory files without `/digital-twin:propose-rules` review.
- NEVER claim a finding without quoting corpus evidence.
- NEVER omit a section if no evidence is found — leave it explicitly empty with a `_no evidence_` marker.

## Roadmap

See `references/methodology.md` § "Roadmap". Next: per-section recommendation extraction from deep-read reports (v0.2), Cursor adapter (v0.3), marketplace publication (v0.4).
