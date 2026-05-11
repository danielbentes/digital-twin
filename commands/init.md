---
name: digital-twin:init
description: Full first-time digital-twin run. Phases 1-6 + a JSON-extraction pass to produce PROFILE.html (card-styled), PROFILE.md, twin.md sub-agent, CLAUDE.md patch, gotchas, and canonical numbers. ~65-95 minutes.
---

# /digital-twin init

First-time run of the digital-twin pipeline.

## What this does

1. **Phase 1 (setup, ~2 min)** — Verify `~/.claude/projects/` exists, count session files + prompts, ask for local UTC offset, confirm identity on shared machines.
2. **Phase 2 (extract, ~3 min)** — `scripts/extract-corpus.py` produces 4 corpus jsonls.
3. **Phase 3 (quantitative, ~3 min)** — `scripts/quantitative.py` + `scripts/temporal.py` in parallel.
4. **Phase 4 (qualitative agents, ~20 min)** — Dispatch 6 `general-purpose` agents in parallel. Each reads the corpus from a specific angle and writes a 1500-2500 word free-form deep read.
5. **Phase 4.5 (insights extraction, ~2 min, ~$1)** — Single Sonnet call distills the 6 deep reads + corpus stats into 7 structured JSON files (`project_areas`, `interaction_style`, `big_wins`, `friction`, `suggestions`, `horizon`, `fun_ending`). These directly feed the card sections in PROFILE.html.
6. **Phase 5 (deep sources, ~15 min)** — `memory-inventory.py`, `plan-inventory.py`, `assistant-turn-mining.py`, optional `pr-comment-mining.sh` in parallel.
7. **Phase 6 (synthesize, ~10 min)** — `scripts/synthesize.py` fills the templates and writes PROFILE.md, PROFILE.html, twin.md, CLAUDE-md-patch.md, gotchas.md, numbers.md.

Total wall-clock: ~65-95 minutes. Cost (model API): ~$5-9 total — Sonnet for agents (~$4-8) + Sonnet for extraction (~$1).

## How to run

The slash command should drive these steps in order. Phase 4 is the only step that requires Claude (the operator) to do something other than `Bash` — it must dispatch parallel `Task`/`Agent` tool calls.

### Phase 1 — setup

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/skills/digital-twin/scripts/extract-corpus.py --count-only
```

Use `AskUserQuestion` to gather:
- **Identity**: "Are you the original prompt author for these logs?"
- **TZ offset**: "What's your local timezone offset from UTC (e.g., 2 for CEST)?" — store as `TZ_OFFSET`.
- **PR mining**: "Run optional `gh api` PR comment mining? Requires `gh auth login`."

If the corpus has <500 prompts, warn and offer to defer.

### Phase 2 — extract

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/skills/digital-twin/scripts/extract-corpus.py
```

### Phase 3 — quantitative + temporal (parallel)

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/skills/digital-twin/scripts/quantitative.py &
python3 ${CLAUDE_PLUGIN_ROOT}/skills/digital-twin/scripts/temporal.py --tz-offset-hours "$TZ_OFFSET" &
wait
```

### Phase 4 — dispatch 6 deep-read agents (parallel)

Read each of these 6 prompt templates, substitute the placeholders (`{{USER_NAME}}`, `{{PROMPT_COUNT}}`, `{{CORPUS_PATH}}`, `{{QUANTITATIVE_FACTS}}`, `{{OUTPUT_PATH}}`) from the Phase 3 outputs, then send **one message with 6 parallel `Agent` tool calls**:

| Prompt template (`references/prompts/*-deep-read.md`) | Output path |
|---|---|
| `orchestration-deep-read.md` | `~/.claude/digital-twin/analysis/reports/orchestration.md` |
| `workflow-deep-read.md` | `~/.claude/digital-twin/analysis/reports/workflow.md` |
| `quality-deep-read.md` | `~/.claude/digital-twin/analysis/reports/quality.md` |
| `encoded-rules-deep-read.md` | `~/.claude/digital-twin/analysis/reports/encoded-rules.md` |
| `planning-style-deep-read.md` | `~/.claude/digital-twin/analysis/reports/planning-style.md` |
| `failure-recovery-deep-read.md` | `~/.claude/digital-twin/analysis/reports/failure-recovery.md` |

Each agent: `subagent_type=general-purpose`, prompt body = filled template, model = `sonnet`. The agent reads the corpus, then writes its report to the named path. Do NOT pass the corpus content inline — paths-only briefing.

Wait for all 6 to finish before continuing.

### Phase 4.5 — extract structured insights (single Sonnet call)

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/skills/digital-twin/scripts/extract-insights.py \
  --user-name "$USER_NAME"
```

This reads the 6 reports + the JSON stats from Phase 3 and writes 7 JSON files to `~/.claude/digital-twin/analysis/insights/`. If it fails (LLM error, bad JSON), `synthesize.py` falls back to Tier 2 (rule-based card builders) — pipeline never hard-fails.

### Phase 5 — deep sources (parallel)

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/skills/digital-twin/scripts/memory-inventory.py &
python3 ${CLAUDE_PLUGIN_ROOT}/skills/digital-twin/scripts/plan-inventory.py &
python3 ${CLAUDE_PLUGIN_ROOT}/skills/digital-twin/scripts/assistant-turn-mining.py &
bash  ${CLAUDE_PLUGIN_ROOT}/skills/digital-twin/scripts/pr-comment-mining.sh &
wait
```

### Phase 6 — synthesize

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/skills/digital-twin/scripts/synthesize.py \
  --user-name "$USER_NAME"
open ~/.claude/digital-twin/PROFILE.html   # macOS; xdg-open on Linux
```

## Outputs

After successful completion:

- `~/.claude/digital-twin/PROFILE.html` — card-styled report (open in browser)
- `~/.claude/digital-twin/PROFILE.md` — markdown mirror of PROFILE.html
- `~/.claude/agents/twin.md` — installable sub-agent that imitates the operator
- `~/.claude/digital-twin/CLAUDE-md-patch.md` — patch to copy into `~/.claude/CLAUDE.md`
- `~/.claude/digital-twin/gotchas.md` — per-user gotchas catalog
- `~/.claude/digital-twin/numbers.md` — canonical numbers source-of-truth
- `~/.claude/digital-twin/corpora/*.jsonl` — raw corpora for re-analysis
- `~/.claude/digital-twin/analysis/*.json|.md` — intermediate analysis
- `~/.claude/digital-twin/analysis/insights/*.json` — structured card data (7 files)
- `~/.claude/digital-twin/analysis/reports/*.md` — the 6 free-form deep-read reports

## Privacy

Fully local. No network calls except (a) Phase 4 agent dispatch via your Claude Code session and (b) Phase 4.5 extraction via Sonnet (both go through your existing Claude Code auth). No telemetry. No corpus content leaves the machine outside those LLM calls.

## On failure

Each phase writes to disk before the next starts, so partial failures leave usable artifacts. If Phase 4 fails (agent dispatch issues), `extract-insights.py` skips (Tier 3) and `synthesize.py` produces a profile with rule-based card content (Tier 2). Re-run just Phase 4 later to upgrade to Tier 1.
