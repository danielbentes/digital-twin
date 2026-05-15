---
name: digital-twin:propose-rules
description: Review pending memory rule and principle proposals from the digital-twin pushback detector. Approves or rejects each proposed correction before it lands in the user's memory.
---

# /digital-twin propose-rules

Review and approve auto-detected rule/principle corrections.

## How it works

The `pushback-detector.py` watches `(assistant-turn, user-reply)` pairs and drafts candidate memory files when it sees a pushback that isn't already encoded in an existing rule or principle. Proposals live at:

```
~/.claude/digital-twin/proposed-rules/
```

Each proposal is a canonical-format memory file (YAML frontmatter + correction body + evidence section). Filenames are prefixed with a 3-digit confidence score (e.g., `090_<hash>_<slug>.md` for confidence 0.90).

## Procedure (when this command is invoked)

Execute these steps in order:

### 1. Refresh proposals (optional)

Ask the user: "Run the pushback detector first to catch new pushbacks since last review? (y/n)". If yes:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/skills/digital-twin/scripts/pushback-detector.py --max-proposals 20
```

### 2. List pending proposals

```bash
ls -1 ~/.claude/digital-twin/proposed-rules/*.md 2>/dev/null | sort -r
```

If empty, report "No pending proposals." and exit.

### 3. For each proposal (highest confidence first):

1. **Read** the proposal file fully (`Read` tool).
2. **Present** to the user in this format:

```
Proposal X/N — <slug>  (confidence: 0.XX)

Evidence
  Project:    <project>
  Date:       <YYYY-MM-DD>
  Assistant:  > <truncated assistant turn, 200 chars>
  User reply: > <truncated user reply, 300 chars>

Proposed correction
  Name:        <name>
  Description: <description>
  Type:        feedback
  Body:
    Judgment correction:
    Underlying principle:
    Rationale:
    Applies when:
    Does not apply when:
    Failure mode:
    Trust/delegation implication:

[a]pprove · [r]eject · [d]efer · [e]dit · [s]kip-all
```

3. **Wait** for the user's response. Use `AskUserQuestion` with header "Review" if available; otherwise read the user's chat reply.

4. **Act on the response:**

   - **approve (`a`)**: First check the proposal body for unresolved scaffold text. If it still contains `_Fill in`, `TODO`, or an empty required section for Underlying principle, Rationale, Applies when, Does not apply when, Failure mode, or Trust/delegation implication, require `edit` first and do not approve. Then ask which project's memory to write to (list projects from `~/.claude/projects/`). Then:
     a. Strip the `<!-- AUTO-PROPOSED ... -->` comments and the `## Evidence` section from the body.
     b. Write the cleaned principle-rich correction to `~/.claude/projects/<chosen-project>/memory/<name>.md`.
     c. Append a one-line entry to that project's `MEMORY.md` index (create the file if it doesn't exist).
     d. Move the original proposal to `~/.claude/digital-twin/proposed-rules/archive/approved_<filename>`.
     e. Confirm: "Approved → ~/.claude/projects/<project>/memory/<name>.md".

   - **reject (`r`)**: Ask "Why? (one line, optional)". Move the proposal to `~/.claude/digital-twin/proposed-rules/archive/rejected_<filename>`. Append the rejection reason as an HTML comment at the top of the archived file. Never delete — rejections are reviewable.

   - **edit (`e`)**: Open an inline edit dialogue. Read the proposal, ask the user to provide replacement text for the correction body (everything between the frontmatter and the `## Evidence` section). Update the file in place. Then re-present the updated proposal for a/r/d.

   - **defer (`d`)**: Leave the file in place. Continue to the next proposal.

   - **skip-all (`s`)**: Stop processing. Remaining proposals stay queued.

### 4. Summary

After all proposals are handled (or the user skips), print:

```
Session summary:
  approved: X
  rejected: Y
  edited:   Z
  deferred: W
```

## Guarantees

- **Never auto-writes to memory.** Every approval requires explicit user confirmation of the target project.
- **Never deletes proposals.** Rejected/approved proposals move to `archive/` for audit.
- **Idempotent.** The detector's content-hash dedup means re-running the detector after approving doesn't recreate identical proposals.

## Tuning

If too many proposals come through (false positive rate too high), raise the minimum confidence:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/skills/digital-twin/scripts/pushback-detector.py --min-confidence 0.6
```

If proposals are missing real pushbacks, lower it:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/skills/digital-twin/scripts/pushback-detector.py --min-confidence 0.3
```

The current default (0.4) is tuned for ~15% true-positive rate on the v0.1 corpus.

## When to run

- **Weekly** during normal usage to catch new patterns.
- **After a session with many pushbacks** (you'll feel it).
- **Before re-running `/digital-twin update`** so the refreshed profile includes any newly-approved rules.

## Privacy

Every proposal stays local. The `~/.claude/digital-twin/proposed-rules/` directory should be gitignored if `$HOME` is under version control.
