---
name: digital-twin:init
description: Full first-time digital-twin run. Walks the user through Phase 1 setup, then dispatches Phases 2-6 to produce PROFILE.md, twin.md, CLAUDE.md patch, gotchas, and canonical numbers. ~60-90 minutes.
---

# /digital-twin init

First-time run of the digital-twin pipeline.

## What this does

1. **Phase 1 (setup, ~2 min):** Verify the user's `~/.claude/projects/` exists, count session files and prompts, warn if the corpus is too small, confirm identity on shared machines.
2. **Phase 2 (extract, ~3 min):** Run `scripts/extract-corpus.py` to produce 4 corpus jsonls.
3. **Phase 3 (quantitative, ~3 min):** Run `scripts/quantitative.py` and `scripts/temporal.py`.
4. **Phase 4 (qualitative agents, ~20 min parallel):** Fill the 6 templated prompts and dispatch 6 `general-purpose` agents in parallel. Each writes a 1500-2500 word deep read.
5. **Phase 5 (deep sources, ~15 min parallel):** Run memory-inventory.py, plan-inventory.py, assistant-turn-mining.py, and (optionally) pr-comment-mining.sh.
6. **Phase 6 (synthesize, ~10 min):** Run `scripts/synthesize.py` to produce the final artifacts.

Total wall-clock: ~60-90 minutes.

## How to run

The user invokes `/digital-twin init` and the skill executes:

```bash
# Phase 1: setup
python3 ${CLAUDE_PLUGIN_ROOT}/skills/digital-twin/scripts/extract-corpus.py --count-only

# Phase 2: extract
python3 ${CLAUDE_PLUGIN_ROOT}/skills/digital-twin/scripts/extract-corpus.py

# Phase 3: quantitative + temporal (parallel)
# Before running, ask the user (via AskUserQuestion) for their local UTC offset
# in hours, then substitute it into TZ_OFFSET below.
TZ_OFFSET=$(date +%z | sed 's/00$//' | sed 's/^+//')   # fallback: system zone
python3 ${CLAUDE_PLUGIN_ROOT}/skills/digital-twin/scripts/quantitative.py &
python3 ${CLAUDE_PLUGIN_ROOT}/skills/digital-twin/scripts/temporal.py --tz-offset-hours "$TZ_OFFSET" &
wait

# Phase 4: dispatch 6 qualitative agents in parallel
# (this is done by the skill harness, not a single bash command — see SKILL.md)

# Phase 5: deep sources (parallel)
python3 ${CLAUDE_PLUGIN_ROOT}/skills/digital-twin/scripts/memory-inventory.py &
python3 ${CLAUDE_PLUGIN_ROOT}/skills/digital-twin/scripts/plan-inventory.py &
python3 ${CLAUDE_PLUGIN_ROOT}/skills/digital-twin/scripts/assistant-turn-mining.py &
bash ${CLAUDE_PLUGIN_ROOT}/skills/digital-twin/scripts/pr-comment-mining.sh &
wait

# Phase 6: synthesize
python3 ${CLAUDE_PLUGIN_ROOT}/skills/digital-twin/scripts/synthesize.py
```

## Outputs

After successful completion:

- `~/.claude/digital-twin/PROFILE.md` — the user's behavioral profile
- `~/.claude/agents/twin.md` — the installable subagent
- `~/.claude/digital-twin/CLAUDE-md-patch.md` — patch to copy into ~/.claude/CLAUDE.md
- `~/.claude/digital-twin/gotchas.md` — per-user gotchas catalog
- `~/.claude/digital-twin/numbers.md` — canonical numbers source-of-truth
- `~/.claude/digital-twin/corpora/*.jsonl` — raw corpora for re-analysis
- `~/.claude/digital-twin/analysis/*.json|.md` — intermediate analysis outputs

## Privacy

Fully local. No network calls except optional `gh api` for PR mining. No telemetry. No data leaves the machine.

## Confirmation prompts

Before starting, ask the user to confirm:

1. **Identity:** "Are you the original prompt author for the logs under `~/.claude/projects/`? (Shared-machine check.)"
2. **TZ offset:** "What's your local timezone offset from UTC? (Used for hour-of-day analysis.)"
3. **Skip PR mining?** "Mine recent GitHub PRs via `gh`? Requires `gh auth login`. (Optional.)"

If the corpus has <500 prompts, warn and offer to defer.

## On failure

Each phase writes to disk before the next starts, so partial failures leave usable artifacts. If Phase 4 fails (agent dispatch issues), Phase 6 will write a profile with `_pending_` markers in qualitative sections — the user can re-run just Phase 4 later.
