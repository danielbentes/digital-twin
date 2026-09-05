---
name: digital-twin:status
description: Show the current state of the user's digital-twin artifacts — last-run timestamp, corpus size, drift since last run, twin agent install status.
---

# /digital-twin:status

Read-only status check.

## What this does

1. Reads `~/.claude/digital-twin/_synthesis.json` to get last-run metadata.
2. Counts current prompts (via `extract-corpus.py --count-only`) and compares to last run.
3. Checks `~/.claude/agents/twin.md` exists.
4. Reports drift signals (new pushback patterns, vocabulary changes).
5. Counts pending pushback-derived rule proposals in `~/.claude/digital-twin/proposed-rules/` (excluding `archive/`) and reports the count and queue path.

## Output format

```
Digital Twin status — <user>

Last run:        <YYYY-MM-DD> (<N> days ago)
Profile version: <v0.X>
Prompt corpus:   <N> → <N+delta> (<+delta>, <+delta%>)
Session files:   <N> → <N+delta>
Memory files:    <N> → <N+delta>
Plans:           <N> → <N+delta>
Twin agent:      installed at ~/.claude/agents/twin.md
CLAUDE.md patch: drafted at ~/.claude/digital-twin/CLAUDE-md-patch.md
                 (not yet copied to ~/.claude/CLAUDE.md)
Pending proposals: <N> at ~/.claude/digital-twin/proposed-rules/
                   (review with /digital-twin:propose-rules)

Drift since last run:
- <N> new memory files (run /digital-twin update to incorporate)
- <N> new pushback first-words detected
- <N> new prompts (corpus growth: <pct>%)
- <N> pending rule proposals awaiting review

Recommendations:
- <generated based on thresholds — e.g., "No action needed" / "Run /digital-twin:update" / "Run /digital-twin:propose-rules">
```

## When to run

- Daily / weekly habit
- Before deciding whether `/digital-twin:update` is worth running
- When the twin agent's output feels stale
- When the PostToolUse hook is installed, to keep the proposal queue from backing up silently

## Implementation note

This is a pure-read command. It writes nothing. Even the count-only extract pass goes to /dev/null.

## On first-run

If `_synthesis.json` doesn't exist, output:

```
No digital twin found. Run /digital-twin:init to build your first profile (~60-90 minutes).
```

The pending-proposal count is still reported on first run: if the hook is installed, proposals may already be queued.
