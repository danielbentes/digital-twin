# Session log extraction schema

Claude Code stores session logs as JSONL files at `~/.claude/projects/<project-slug>/<uuid>.jsonl`. Each line is one JSON entry. This document describes the entry types the `digital-twin` skill cares about and how it extracts user prompts.

## Entry types

| `type` field | Meaning | Used by digital-twin? |
| --- | --- | --- |
| `last-prompt` | Truncated user prompt (~201 chars) cached per session for analytics | YES — primary corpus source |
| `user` | Full user message, may be string or content-block list | YES — used for long-prompt extraction |
| `assistant` | Assistant message | YES — for assistant-turn-mining only |
| `human` | (rare) older format for user message | YES — handled as fallback |
| `system` | System reminders and tool meta | NO |
| `attachment` | File attachment metadata | NO |
| `tool_use` / `tool_result` | Tool call records | NO (in v0.1) |
| `queue-operation` | Internal queue meta | NO |
| `permission-mode` | Permission mode changes | NO |

## Prompt extraction rules

The `extract_prompt(obj)` function in `extract-corpus.py` handles three shapes:

### Shape A — `last-prompt`

```json
{"type": "last-prompt", "lastPrompt": "ship it", "timestamp": "2026-05-11T16:23:00Z"}
```

The `lastPrompt` field is the user's prompt, **truncated at approximately 201 characters**. This is the most numerous and easiest-to-mine source but it's lossy for long prompts.

### Shape B — `user` with string content

```json
{"type": "user", "message": {"role": "user", "content": "investigate and fix #80"}}
```

Full text in `message.content` as a string. No truncation.

### Shape C — `user` with content blocks

```json
{
  "type": "user",
  "message": {
    "role": "user",
    "content": [
      {"type": "text", "text": "Here is the failing test:"},
      {"type": "text", "text": "..."}
    ]
  }
}
```

Multiple text blocks; we join them with newlines. Non-text blocks (tool_use, image, etc.) are ignored.

## Auto-wake filtering

The corpus contains automated wake payloads from Paperclip, autonomous loops, and agent self-invocations. These look like prompts but they're not human-typed. We exclude them from `human-first.jsonl` while keeping them in `corpus.jsonl`.

### Auto-wake prefixes (current list)

A prompt is treated as auto-wake if it starts with any of:

- `-\n## Paperclip` — Paperclip heartbeat wake payload (older format)
- `## Paperclip` — Paperclip heartbeat wake payload (newer format)
- `Paperclip Wake Payload`
- `<<autonomous` — sentinels for autonomous-loop modes
- `<<autonomous-loop`
- `<<autonomous-loop-dynamic>>`
- `You are agent` — agent self-invocations / role primers

This list is maintained in the `AUTO_WAKE_PREFIXES` constant in `extract-corpus.py`. New patterns should be added there.

## Project slug normalization

The project directory under `~/.claude/projects/` is a URL-encoded form of the project path. For example:

```
-Users-alice               →  /Users/alice
-Users-alice-code-myapp    →  /Users/alice/code/myapp
```

The skill preserves the slug as-is in the corpus jsonl but uses it as the join key to look up project memory files (`~/.claude/projects/<slug>/memory/*.md`). When displaying to the user, slugs are shown verbatim — decoding adds little value and risks ambiguity.

## Timestamp parsing

Timestamps appear in ISO 8601 format with optional `Z` suffix. The skill normalizes to Python `datetime` via `datetime.fromisoformat(ts.replace("Z", "+00:00"))`. Entries without parseable timestamps are excluded from `timestamped.jsonl` but kept in `corpus.jsonl`.

The temporal-analysis pass takes an optional `--tz-offset-hours` flag to convert to the user's local time zone before computing hour-of-day histograms. The default is UTC.

## What's NOT extracted in v0.1

These could be useful for future versions but are not mined yet:

1. **Tool invocations** — `tool_use` entries reveal what tools the user invoked. v0.2 will mine this for the "tools reach-list" section of the twin.
2. **Attachments** — file paths and types attached to prompts. v0.2 candidate.
3. **Permission modes** — when the user toggled permission modes. v0.3 candidate.
4. **Compaction events** — `compact` markers in the log. v0.3 candidate (useful for detecting "context-overflow" patterns).
5. **Hooks output** — hook-injected context (e.g., `<user-prompt-submit-hook>` blocks). Out of scope for v1.0; would require deeper schema work.

If your analysis needs these, add a new pass; do not retrofit `extract-corpus.py`. Each pass should have one clear purpose.
