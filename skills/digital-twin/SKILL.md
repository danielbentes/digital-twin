---
name: digital-twin
version: 0.1.0
description: |
  Mine the user's own Claude Code session logs to build a behavioral profile
  and an installable subagent that mirrors how they actually orchestrate Claude
  Code. Produces a personalized PROFILE.md, a twin.md subagent, a CLAUDE.md
  patch, a per-user gotchas catalog, and a canonical numbers source-of-truth —
  all from local jsonl logs in 60-90 minutes.

  Use when the user says any of: "build a digital twin of me", "make a personal
  agent from my prompts", "analyze my Claude Code usage", "mine my session
  logs", "I want a twin agent", "build an agent that acts like me", "encode my
  workflow as a subagent", "create a personalized orchestrator".

  This skill MUST be consulted for those requests because no other skill or
  generic agent can produce a personalized orchestrator from log mining —
  generic best-practice agents won't capture the user's specific conventions,
  vocabulary, project glossary, pushback triggers, or recovery cycles. Even if
  the user thinks they want a "generic helpful agent", the digital-twin output
  is materially different: it quotes their actual prompts, encodes their actual
  memory rules, and matches their actual voice.
---

# Digital Twin

Build a personalized Claude Code subagent from the user's own session logs.

## What this skill produces

After a full run, the user has:

| Artifact | Path | Purpose |
|---|---|---|
| Profile | `~/.claude/digital-twin/PROFILE.md` | Behavioral analysis (~30-50 KB) |
| Subagent | `~/.claude/agents/twin.md` | Installable orchestrator |
| CLAUDE.md patch | `~/.claude/digital-twin/CLAUDE-md-patch.md` | Global defaults addendum |
| Gotchas card | `~/.claude/digital-twin/gotchas.md` | Per-user gotchas catalog |
| Canonical numbers | `~/.claude/digital-twin/numbers.md` | Verification source-of-truth |
| Raw corpora | `~/.claude/digital-twin/corpora/*.jsonl` | For re-analysis |

## When to use this skill

- User asks for a "digital twin" / "personal agent" / "subagent that acts like me"
- User says "analyze my Claude Code usage" or "mine my prompt logs"
- User has been using Claude Code for 4+ weeks and wants an automation layer
- User wants to install a CLAUDE.md or subagent based on observed behavior
- User invokes `/digital-twin init`, `/digital-twin update`, `/digital-twin status`, or `/digital-twin propose-rules`

## When NOT to use this skill

- User has fewer than ~500 prompts in their corpus — insufficient signal, run `scripts/extract-corpus.py --count-only` to verify and warn
- User wants a generic best-practice agent — point them at standard Claude Code skills
- User wants live behavioral monitoring without an initial mine — direct them to run `/digital-twin init` first
- User is on a shared machine and might not be the original prompt author — confirm identity in Phase 1 before proceeding

## Workflow overview

See `references/methodology.md` for the full step-by-step.

| Phase | Wall-clock | What happens |
|---|---|---|
| 1. Setup | ~2 min | Verify session log presence, count files, propose scope |
| 2. Extract | ~3 min | `scripts/extract-corpus.py` produces corpus jsonls |
| 3. Quantitative | ~3 min | `scripts/quantitative.py` + `scripts/temporal.py` |
| 4. Qualitative agents | ~20 min (parallel) | 6 general-purpose agents reading corpus from different angles |
| 5. Deep sources | ~15 min (parallel) | memory + plans + assistant turns + PR comments |
| 6. Synthesize | ~10 min | `scripts/synthesize.py` fills templates |

**Total: ~60-90 minutes wall-clock** on a typical 5k-15k prompt corpus.

## Phase 1 — Setup checklist

Before extracting anything, verify:

1. `~/.claude/projects/` exists and has at least one project subdirectory
2. Total jsonl line count across all project files (use `find ~/.claude/projects -name '*.jsonl' | xargs wc -l`)
3. If <500 user-typed prompts (after Paperclip filtering): warn and suggest waiting
4. If >50,000 prompts: warn that synthesis may take longer; offer `--sample` mode
5. Confirm the user is the original prompt author (shared machine check)

## Phase 2 — Extract

```bash
python3 ~/.claude/skills/digital-twin/scripts/extract-corpus.py \
  --source ~/.claude/projects \
  --out ~/.claude/digital-twin/corpora
```

Produces:
- `corpus.jsonl` — all `last-prompt` entries (truncated to ~201 chars)
- `first-prompts.jsonl` — first prompt of each session
- `human-first.jsonl` — long, high-signal real human-typed first prompts (excludes Paperclip)
- `timestamped.jsonl` — prompts with timestamps for temporal analysis
- `_summary.json` — file counts, prompt counts, project list

## Phase 3 — Quantitative

```bash
python3 ~/.claude/skills/digital-twin/scripts/quantitative.py \
  --corpus ~/.claude/digital-twin/corpora/corpus.jsonl \
  --out ~/.claude/digital-twin/analysis/numbers.json

python3 ~/.claude/skills/digital-twin/scripts/temporal.py \
  --timestamped ~/.claude/digital-twin/corpora/timestamped.jsonl \
  --out ~/.claude/digital-twin/analysis/temporal.json
```

## Phase 4 — Qualitative agents (parallel)

Dispatch 6 `general-purpose` agents using the templated prompts in `references/prompts/`. Each reads the corpus from a specific angle and writes a structured report. Dispatch them in a single message with parallel Agent tool calls.

The prompts to use:
1. `references/prompts/orchestration-deep-read.md` — how the user delegates
2. `references/prompts/workflow-deep-read.md` — issue → plan → spec → impl → verify → ship
3. `references/prompts/quality-deep-read.md` — pushback, conventions, voice
4. `references/prompts/encoded-rules-deep-read.md` — memory rules survey
5. `references/prompts/planning-style-deep-read.md` — plan archetypes
6. `references/prompts/failure-recovery-deep-read.md` — convergence pairs

Each placeholder (`{{USER_NAME}}`, `{{PROMPT_COUNT}}`, `{{CORPUS_PATH}}`, etc.) is filled from Phase 3 outputs before dispatch.

## Phase 5 — Deep sources (parallel)

```bash
python3 ~/.claude/skills/digital-twin/scripts/memory-inventory.py
python3 ~/.claude/skills/digital-twin/scripts/plan-inventory.py
python3 ~/.claude/skills/digital-twin/scripts/assistant-turn-mining.py
bash ~/.claude/skills/digital-twin/scripts/pr-comment-mining.sh  # optional, needs gh CLI
```

## Phase 6 — Synthesize

```bash
python3 ~/.claude/skills/digital-twin/scripts/synthesize.py \
  --analysis ~/.claude/digital-twin/analysis \
  --out ~/.claude/digital-twin
```

Fills templates from `references/profile-template.md`, `references/subagent-template.md`, `references/claude-patch-template.md`. Lands final artifacts in `~/.claude/digital-twin/` and `~/.claude/agents/twin.md`.

## Privacy guarantees

- **No network calls** during analysis except optional `gh api` for PR mining
- **No telemetry** — the skill does not phone home
- **Prompts stay local** — corpus jsonls saved in `~/.claude/digital-twin/corpora/` for re-analysis but never uploaded
- **No auto-memory writes** — all self-updating proposals require explicit approval via `/digital-twin propose-rules`
- **No auto-CLAUDE.md edits** — the patch lands as a separate file; user copies what they want

## Slash commands

- `/digital-twin init` — full first-time run (Phases 1-6)
- `/digital-twin update` — re-run Phases 2-6 with new logs since last run
- `/digital-twin status` — show last-run timestamp + corpus size + drift since last run
- `/digital-twin propose-rules` — review pushback-detected rule proposals

## Cost model

- Initial run: ~6 agents × ~80k input tokens + ~12k output each ≈ 540k tokens total
- Estimated on Opus 4.7: $8-15 per first-run
- Update runs: typically ~30% of first-run cost (delta-only)
- Self-updating twin: <$0.10 per detected pushback event

## Critical guardrails (NEVER list)

The synthesized twin agent inherits this NEVER list:

- NEVER commit without explicit user approval
- NEVER force-push to main/master
- NEVER auto-write to memory files without `/digital-twin propose-rules` review
- NEVER claim a finding without quoting corpus evidence
- NEVER omit a section in PROFILE.md if no evidence found — leave it explicitly empty with a `_no evidence_` marker

## Versioning

This is v0.1.0. The roadmap to v1.0 includes multi-language support, Cursor/Aider/Codex log adapters, team profiles, and a full self-updating twin. See `references/methodology.md` § "Roadmap".
