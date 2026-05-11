---
name: digital-twin:update
description: Re-run the digital-twin pipeline against the latest logs, producing updated PROFILE.md, twin.md, and CLAUDE.md patch. Faster than init because it can skip cached quantitative passes.
---

# /digital-twin update

Refresh the digital-twin artifacts against the user's most recent logs.

## What this does

By default, re-runs Phases 2-6 with full recompute. With `--delta`, only re-mines logs newer than `~/.claude/digital-twin/_synthesis.json` `generated_at` timestamp.

## How to run

```bash
# Full update
python3 ~/.claude/skills/digital-twin/scripts/extract-corpus.py
python3 ~/.claude/skills/digital-twin/scripts/quantitative.py
python3 ~/.claude/skills/digital-twin/scripts/temporal.py --tz-offset-hours <local>
# ... (same as init from Phase 2 onward)
python3 ~/.claude/skills/digital-twin/scripts/synthesize.py

# Delta mode (v0.2 feature — not implemented in v0.1)
# python3 ~/.claude/skills/digital-twin/scripts/extract-corpus.py --since <iso-timestamp>
```

## When to run

- After 1+ months of new Claude Code usage
- After a major workflow change (new project, new tool reach, new conventions)
- After accumulating 10+ new memory rules
- After a Claude Code version bump that changes session log format

## Diff from previous run

If `~/.claude/digital-twin/_synthesis.json` exists, the synthesize step populates the `CHANGED_SINCE_LAST_RUN` section in `CLAUDE-md-patch.md` with the deltas:

- New encoded rules
- Vocabulary drift (rising/falling words)
- New project glossary entries
- Pushback trigger changes

## Privacy

Same as init: fully local, no telemetry.

## Estimated cost

~30% of an initial run if no qualitative agents re-dispatched (the deep reads are the expensive part). With `--rerun-agents`, full cost.
