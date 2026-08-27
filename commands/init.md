---
name: digital-twin:init
description: Full first-time digital-twin run. Phases 1-6 + a JSON-extraction pass to produce PROFILE.html (card-styled), PROFILE.md, twin.md sub-agent, CLAUDE.md patch, gotchas, and canonical numbers. Wall-clock dominated by 2 LLM-bound phases; local Python pipeline runs in ~20 seconds.
---

# /digital-twin init

First-time run of the digital-twin pipeline.

## What this does

1. **Phase 1 (setup, seconds)** — Verify `~/.claude/projects/` exists, count session files + prompts, ask for local UTC offset, confirm identity on shared machines.
2. **Phase 2 (extract, ~5 sec / 10k sessions)** — `scripts/extract-corpus.py` produces 4 corpus jsonls.
3. **Phase 3 (quantitative, ~10 sec)** — `scripts/quantitative.py` + `scripts/temporal.py` in parallel.
4. **Phase 4 (deep sources, ~5 sec total)** — `memory-inventory.py`, `plan-inventory.py`, `assistant-turn-mining.py`, optional `pr-comment-mining.sh` in parallel. These files feed both the deep-read prompts and the twin spec.
5. **Phase 5 (qualitative agents, LLM-bound)** — Dispatch 6 `general-purpose` agents in parallel. Each reads the corpus from a specific angle and writes a 1500-2500 word free-form deep read. Wall-clock depends on model latency and parallel-dispatch overhead; budget the bulk of the run here.
6. **Phase 5.5 (insights extraction, 3-10+ min, ~$0.50-1)** — Single Sonnet call distills the 6 deep reads + corpus stats (~180 KB prompt) into 7 structured JSON files (`project_areas`, `interaction_style`, `big_wins`, `friction`, `suggestions`, `horizon`, `fun_ending`). Default timeout is 15 min; pass `--timeout` for larger corpora. On overrun, falls through to Tier 2.
7. **Phase 5.6 (behavioral twin spec, 3-10+ min)** — `scripts/extract-twin-spec.py` distills the reports, insights, stats, and deep-source inventories into `analysis/twin-spec.json`, the compact substitution contract used by `twin.md` and generated CLAUDE rules. This includes authority boundaries, principles, trust behavior, and agent-supervision policy.
8. **Phase 6 (synthesize, <1 sec)** — `scripts/synthesize.py` fills the templates and writes PROFILE.md, PROFILE.html, twin.md, CLAUDE-md-patch.md, generated rules, gotchas.md, numbers.md.

**Local pipeline (Phases 2, 3, 4, 6): ~20 sec on a 10k-session corpus.** Phases 5, 5.5, and 5.6 are LLM-bound and dominate wall-clock — there is no useful fixed estimate for those because agent latency and prompt size vary too much. Cost: ~$5-9 total (Sonnet for 6 deep-read agents + two extraction calls).

## How to run

The slash command should drive these steps in order. Phase 5 is the only step that requires Claude (the operator) to do something other than `Bash` — it must dispatch parallel `Task`/`Agent` tool calls.

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

### Phase 4 — deep sources (parallel)

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/skills/digital-twin/scripts/memory-inventory.py &
python3 ${CLAUDE_PLUGIN_ROOT}/skills/digital-twin/scripts/plan-inventory.py &
python3 ${CLAUDE_PLUGIN_ROOT}/skills/digital-twin/scripts/assistant-turn-mining.py &
bash  ${CLAUDE_PLUGIN_ROOT}/skills/digital-twin/scripts/pr-comment-mining.sh &
wait
```

Run this before dispatching deep-read agents. The prompt templates need the memory, plan, and convergence outputs as both counts and paths; `extract-twin-spec.py` also uses these files as operational evidence.

### Phase 5 — dispatch 6 deep-read agents (parallel)

Read each of the 6 prompt templates in `${CLAUDE_PLUGIN_ROOT}/skills/digital-twin/references/prompts/`. Each template uses `{{PLACEHOLDER}}` markers. Fill **every** placeholder before dispatch — agents see the literal `{{...}}` if you skip one.

Fill sources (read these once, reuse for all 6 prompts):
- **`numbers.json`** (Phase 3a output) → `USER_NAME` (from `--user-name` arg), `PROMPT_COUNT` = `n_prompts`, `DATE_RANGE` (build `"<start> → <end>"` from `temporal.json::date_range`), `N_FEEDBACK_RULES`, `N_PROJECT_MEMORIES`, `N_USER_MEMORIES`, `N_REFERENCE_MEMORIES` (compute from `memory-inventory.json::by_type`).
- **`temporal.json`** (Phase 3b output) → `DATE_RANGE` as above.
- **`plan-inventory.json`** (Phase 4 output) → `N_PLANS`, `N_SURGICAL` = `archetypes.surgical`, `N_MULTIPHASE` = `archetypes.multi-phase`, `N_WITH_OOS` = `has_oos_count`, `AVG_AC_COUNT` = `avg_ac_count`, `DRIFT_SUMMARY` = JSON-stringified `drift` field (or `"insufficient plans for drift"` if null).
- **`convergence-pairs.json`** (Phase 4 output) → `N_PAIRS` = `n_pairs`, `N_APPROVALS` = `counts.approval`, `N_EXPLICIT_PB` = `counts.explicit_pushback`, `N_IMPLICIT_PB` = `counts.implicit_pushback`, `PUSHBACK_RATIO` = `(explicit_pushback + implicit_pushback) / n_pairs`, `MEDIAN_APPROVED` and `MEDIAN_PUSHBACK` from `median_length_chars`.
- **Path placeholders** (literal absolute paths under `~/.claude/digital-twin/`):
  - `CORPUS_PATH` → `~/.claude/digital-twin/corpora/corpus.jsonl`
  - `HUMAN_FIRST_PATH` → `~/.claude/digital-twin/corpora/human-first.jsonl`
  - `HUMAN_FIRST_COUNT` → from `~/.claude/digital-twin/corpora/_summary.json::n_human_first_prompts`
  - `MEMORY_INVENTORY_PATH` → `~/.claude/digital-twin/analysis/memory-inventory.json`
  - `RULES_MD_PATH` → `~/.claude/digital-twin/analysis/rules.md`
  - `PLAN_INVENTORY_PATH` → `~/.claude/digital-twin/analysis/plan-inventory.json`
  - `CONVERGENCE_PAIRS_PATH` → `~/.claude/digital-twin/analysis/convergence-pairs.json`
  - `PUSHBACK_TRIGGERS_PATH` → `~/.claude/digital-twin/analysis/pushback-triggers.md`
  - `PUSHBACK_QUOTES_PATH` → same as `PUSHBACK_TRIGGERS_PATH` (the longest-pushback samples live in that file).
- **`QUANTITATIVE_FACTS`** → a 5-10 line summary block built from `numbers.json` (top fields: n_prompts, n_projects, avg/median/p90 prompt length, slash share, dominant non-English language).
- **`OUTPUT_PATH`** → per-prompt, see the table below.

Then send **one message with 6 parallel `Agent` tool calls**:

| Prompt template (`references/prompts/*-deep-read.md`) | `OUTPUT_PATH` |
|---|---|
| `orchestration-deep-read.md` | `~/.claude/digital-twin/analysis/reports/orchestration.md` |
| `workflow-deep-read.md` | `~/.claude/digital-twin/analysis/reports/workflow.md` |
| `quality-deep-read.md` | `~/.claude/digital-twin/analysis/reports/quality.md` |
| `encoded-rules-deep-read.md` | `~/.claude/digital-twin/analysis/reports/encoded-rules.md` |
| `planning-style-deep-read.md` | `~/.claude/digital-twin/analysis/reports/planning-style.md` |
| `failure-recovery-deep-read.md` | `~/.claude/digital-twin/analysis/reports/failure-recovery.md` |

Each agent: `subagent_type=general-purpose`, prompt body = filled template, model = `sonnet`. The agent reads the corpus, then writes its report to the named path. Do NOT pass the corpus content inline — paths-only briefing.

Wait for all 6 to finish before continuing.

**Sanity check before dispatch:** grep each filled prompt for `{{` — if any survive, you missed a placeholder.

### Phase 5.5 — extract structured insights (single Sonnet call)

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/skills/digital-twin/scripts/extract-insights.py \
  --user-name "$USER_NAME"
```

This reads the 6 reports + the JSON stats from Phase 3 and writes 7 JSON files to `~/.claude/digital-twin/analysis/insights/`. If it fails (LLM error, bad JSON), `synthesize.py` falls back to Tier 2 (rule-based card builders) — pipeline never hard-fails.

### Phase 5.6 — extract behavioral twin spec

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/skills/digital-twin/scripts/extract-twin-spec.py \
  --user-name "$USER_NAME"
```

This writes `~/.claude/digital-twin/analysis/twin-spec.json`. It is the source of truth for `~/.claude/agents/twin.md` and `~/.claude/digital-twin/rules/*.md`. It must run after Phase 4 so the spec has memory, plan, convergence, and trust evidence. The extractor stamps the current `v0.4` `$schema_version`; synthesis migrates the documented historical compatibility shape before validating it. See `MIGRATIONS.md`. If it is missing or invalid, `synthesize.py` still writes profile artifacts but emits an explicitly degraded twin with an incomplete-spec warning and without claiming user-substitution authority.

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
- `~/.claude/agents/twin.md` — installable sub-agent that acts as the operator's delegate within authority boundaries
- `~/.claude/digital-twin/rules/*.md` — generated user-level rule files for substitution, preferences, workflows, verification, and recovery
- `~/.claude/digital-twin/CLAUDE-md-patch.md` — short install guide that imports the generated rules
- `~/.claude/digital-twin/gotchas.md` — per-user gotchas catalog
- `~/.claude/digital-twin/numbers.md` — canonical numbers source-of-truth
- `~/.claude/digital-twin/corpora/*.jsonl` — raw corpora for re-analysis
- `~/.claude/digital-twin/analysis/*.json|.md` — intermediate analysis
- `~/.claude/digital-twin/analysis/insights/*.json` — structured card data (7 files)
- `~/.claude/digital-twin/analysis/twin-spec.json` — behavioral contract for the replacement twin
- `~/.claude/digital-twin/analysis/reports/*.md` — the 6 free-form deep-read reports

## Privacy

Local extraction/statistics/rendering stay on your machine. The LLM-bound phases use your existing Claude Code auth and can send corpus-derived evidence to Claude: Phase 5 dispatches 6 deep-read agents via the Agent tool, Phase 5.5 makes one profile-insights extraction call via `claude -p`, and Phase 5.6 makes one behavioral-spec extraction call via `claude -p`. No Anthropic API key is required unless `extract-insights.py --allow-sdk-fallback` is explicitly enabled. No plugin telemetry.

## On failure

Each phase writes to disk before the next starts, so partial failures leave usable artifacts. If Phase 5 fails (agent dispatch issues), `extract-insights.py` skips (Tier 3) and `synthesize.py` produces a profile with rule-based card content (Tier 2). Re-run just Phase 5 later to upgrade to Tier 1.
