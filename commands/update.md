---
name: digital-twin:update
description: Re-run the digital-twin pipeline against the latest logs, producing updated PROFILE.md, twin.md, and CLAUDE.md patch. Faster than init because it can skip cached quantitative passes.
---

# /digital-twin update

Refresh the digital-twin artifacts against the user's most recent logs.

## What this does

By default, re-runs Phases 2-6 with full recompute, including the behavioral `twin-spec.json`. With `--delta`, only re-mines logs newer than `~/.claude/digital-twin/_synthesis.json` `generated_at` timestamp.

The current `twin-spec.json` is `v0.4` and includes substitution authority, principles, trust behavior, and agent-supervision policy. An unversioned historical v0.3-shaped spec follows the ordered `v0.3 → v0.4` compatibility migration with conservative defaults; refresh the spec before treating the twin as a user-substituting delegate. See `MIGRATIONS.md`.

## How to run

```bash
# Full update. Replace TZ_OFFSET with the user's UTC offset (the skill should
# either reuse the value cached during /digital-twin init or ask again).
TZ_OFFSET=$(date +%z | sed 's/00$//' | sed 's/^+//')
python3 ${CLAUDE_PLUGIN_ROOT}/skills/digital-twin/scripts/extract-corpus.py
python3 ${CLAUDE_PLUGIN_ROOT}/skills/digital-twin/scripts/quantitative.py
python3 ${CLAUDE_PLUGIN_ROOT}/skills/digital-twin/scripts/temporal.py --tz-offset-hours "$TZ_OFFSET"
python3 ${CLAUDE_PLUGIN_ROOT}/skills/digital-twin/scripts/memory-inventory.py
python3 ${CLAUDE_PLUGIN_ROOT}/skills/digital-twin/scripts/plan-inventory.py
python3 ${CLAUDE_PLUGIN_ROOT}/skills/digital-twin/scripts/assistant-turn-mining.py
# ... run/reuse deep-read reports + insights as in init
python3 ${CLAUDE_PLUGIN_ROOT}/skills/digital-twin/scripts/extract-twin-spec.py
python3 ${CLAUDE_PLUGIN_ROOT}/skills/digital-twin/scripts/synthesize.py

# Delta mode (v0.2 — not implemented in v0.1). The --since flag would take an
# ISO 8601 timestamp from ~/.claude/digital-twin/_synthesis.json::generated_at.
# python3 ${CLAUDE_PLUGIN_ROOT}/skills/digital-twin/scripts/extract-corpus.py --since "$LAST_RUN_ISO"
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

~30% of an initial run if no qualitative agents are re-dispatched (the deep reads are the expensive part). Even when reports are reused, refresh `analysis/twin-spec.json` before synthesis whenever stats, insights, memory inventories, or trust/delegation signals changed; never silently reuse a stale behavioral spec for user-substitution. With `--rerun-agents`, full cost.
