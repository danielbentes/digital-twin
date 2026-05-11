{{!--
  orchestration-deep-read.md — qualitative agent prompt template.
  Used by synthesize.py / the skill harness to spawn a general-purpose agent
  that produces a deep read on "how this user delegates and orchestrates Claude
  Code". Placeholders in `{{double_braces}}` are filled before dispatch.
--}}

You are analyzing a corpus of **{{PROMPT_COUNT}}** prompts that **{{USER_NAME}}** has sent to Claude Code over **{{DATE_RANGE}}**. Your job is to characterize **HOW THEY ORCHESTRATE Claude Code** — how they delegate work, when they fan out to multiple agents, how they hand off context, and what their default execution model looks like.

You are NOT writing a generic best-practice guide. You are reverse-engineering one specific operator's style from their actual prompts.

## Corpus access

Two corpus files are available on disk:

1. `{{CORPUS_PATH}}` — {{PROMPT_COUNT}} prompts as JSONL (one per line). Fields: `project`, `session`, `type`, `text`, `ts`. The `text` field is the user's prompt (some are truncated at ~201 chars).
2. `{{HUMAN_FIRST_PATH}}` — {{HUMAN_FIRST_COUNT}} longer, high-signal real human-typed first-prompts-of-session, excluding automated wake payloads.

For broader analysis, prefer the corpus file. For voice and verbatim quotes, prefer the human-first file.

## Quantitative facts (already computed — do NOT recompute)

{{QUANTITATIVE_FACTS}}

## What I need from you

Produce a structured Markdown report (~1500-2500 words) covering:

### 1. Delegation patterns
- When does {{USER_NAME}} delegate to subagents vs do it themselves in the main session?
- What kinds of work get sent to parallel agents? What is the typical fan-out (1, 2, 4, 8 agents)?
- Are there specific verbs they use to signal delegation? ("spawn", "use parallel agents", "team of opus")
- Do they invoke specific agent types by name (Plan, Explore, codex, flow:*, claude-obsidian:*, etc.)?

### 2. Context handoff
- How do they brief subagents? Verbose context, terse command, exact file paths, "here's the question"?
- Do they reference earlier conversation, or write self-contained prompts?
- How often do they correct or follow up on subagent output?

### 3. Tool reach
- What tools dominate (Bash, Read, Edit, Write, Agent, Task, slash commands)?
- What tools are conspicuously absent given what they could be doing?
- Are they more "CLI orchestrator" or "code editor"?

### 4. Approval gates and confirmation rhythm
- How often do they pause to approve vs let the agent run autonomously?
- What triggers them to interrupt? (Long pauses, specific keywords, scope drift?)
- What's their typical "permission mode" inferred from prompts?

### 5. Multi-repo and multi-project orchestration
- Do they juggle multiple repos in one session?
- Do they have a "watched repos" pattern, scheduled tasks, or fleet operations?
- Any evidence of a central control plane (issue tracker, Linear, GitHub Projects, Paperclip-style heartbeats)?

### 6. The orchestration archetypes
- Identify 3-5 named archetypes of how they run sessions (e.g., "ship-it sprint", "research dispatch", "review gauntlet", "heartbeat sweep").
- For each, give: trigger phrase, typical duration, typical agent count, characteristic verbs.

## Output rules

- **Quote actual prompt texts verbatim** to back claims. Tag with `[corpus]` for citations.
- If you don't find evidence for a dimension, say so explicitly: **"No evidence in corpus"** — do not invent.
- Lead with the most counterintuitive finding.
- Avoid generic best-practice language — every claim should be specific to {{USER_NAME}}'s observed behavior.
- Use bullet lists, not prose paragraphs, where possible.
- End with a 5-bullet "TL;DR for the twin agent" — what should the twin do by default based on this analysis.

## File output

Write your report to: `{{OUTPUT_PATH}}`

Word target: 1500-2500. Quotes count.
