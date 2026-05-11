---
name: digital-twin:status
description: Show the current state of the user's digital-twin artifacts — last-run timestamp, corpus size, drift since last run, twin agent install status.
---

# /digital-twin status

Read-only status check.

## What this does

1. Reads `~/.claude/digital-twin/_synthesis.json` to get last-run metadata.
2. Counts current prompts (via `extract-corpus.py --count-only`) and compares to last run.
3. Checks `~/.claude/agents/twin.md` exists.
4. Reports drift signals (new pushback patterns, vocabulary changes).

## Output format

```
Digital Twin status — <user>

Last run:        2026-05-11 (1 day ago)
Profile version: v0.1
Prompt corpus:   12,228 → 12,345 (+117, +0.96%)
Session files:   1,139 → 1,142
Memory files:    175 → 178 (+3)
Plans:           41 → 41 (no change)
Twin agent:      installed at ~/.claude/agents/twin.md
CLAUDE.md patch: drafted at ~/.claude/digital-twin/CLAUDE-md-patch.md
                 (not yet copied to ~/.claude/CLAUDE.md)

Drift since last run:
- 3 new memory files (run /digital-twin update to incorporate)
- 0 new pushback first-words detected
- 117 new prompts (insufficient to recompute)

Recommendations:
- No action needed; corpus growth is below 1% threshold.
```

## When to run

- Daily / weekly habit
- Before deciding whether `/digital-twin update` is worth running
- When the twin agent's output feels stale

## Implementation note

This is a pure-read command. It writes nothing. Even the count-only extract pass goes to /dev/null.

## On first-run

If `_synthesis.json` doesn't exist, output:

```
No digital twin found. Run /digital-twin init to build your first profile (~60-90 minutes).
```
