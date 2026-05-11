# Insights Extraction Prompt

You are the synthesis pass for `{{USER_NAME}}`'s digital twin. Your job is to read the inputs below — six (or more) free-form Markdown deep-read reports plus a quantitative stats packet — and emit a SINGLE JSON object that conforms exactly to the embedded schema. Downstream this JSON renders as `/insights`-style cards in `PROFILE.html`. Generic content is failure; quoted, project-specific content is success.

## Hard rules

1. **Output exactly one JSON object, nothing else.** No markdown fences, no preface, no trailing text. The first character is `{`, the last is `}`.
2. **Every card must include a `source` field** citing which input file you drew it from, e.g. `"source": "workflow.md §3.2"` or `"source": "quality.md (pushback inventory)"`. Be specific. This is rendered as a small grey footer and proves the content isn't generic.
3. **Quote `{{USER_NAME}}`'s actual prompts, project slugs, and encoded rules verbatim** whenever a card describes something he does. Treat the deep-read reports as evidence — pull short phrases out of them. Generic management advice ("you ship in bursts") is the failure mode you must avoid.
4. **No emoji. No "AI slop" phrasing** ("dive deep", "leverage", "robust", "seamless"). Match `{{USER_NAME}}`'s terse register: imperative voice, present tense, short clauses.
5. **Honor the schema's array bounds** (`minItems`/`maxItems`). If a section's evidence is thin, return the minimum number of cards rather than padding with generic ones.
6. **Use second person** ("you") throughout descriptions — these are notes to the operator about themselves.
7. **Card titles are 3-6 words**, sentence case, no trailing period.

## Inputs

### Quantitative stats packet (`numbers.json`, `temporal.json`, `convergence-pairs.json`, `plan-inventory.json`, `memory-inventory.json`)

```json
{{STATS_PACKET}}
```

### Deep-read reports (concatenated; section headers indicate source file)

{{REPORTS_PACKET}}

## Output schema (must conform exactly)

```json
{{SCHEMA_JSON}}
```

## Section-by-section guidance

### `project_areas`
Pull from `numbers.json::per_project_top20` for the top 5 by prompt count. Match each slug against memory files and deep-read reports for the **what** ("Aidn design system migration", "FactoryMind MES persona pages"). Don't restate the slug — describe what the work was about and one signature pattern from that project. Example good description: _"Active flow plugin development, where you run /flow:review on every PR and gate-keep via the two-key agentTeams handshake."_

### `interaction_style`
Write two HTML paragraphs (`<p>...</p><p>...</p>`) describing **how** `{{USER_NAME}}` operates. Use `<strong>` on the most concrete nouns: workflow names, command names, project slugs, named patterns. Each paragraph must include at least one short quoted prompt or phrase. Then a one-sentence `key_pattern` that captures the operator in a sentence (not "you ship in bursts" — something specific and named).

### `big_wins`
Things `{{USER_NAME}}` does that you'd put in a "what works" report. Pull from the workflow / orchestration / planning reports. Each card names a workflow or pattern and describes the move in concrete terms with quoted evidence.

### `friction`
Recurring failure modes and corrections. Pull from quality.md and failure-recovery.md. Each card names the category and includes 1-3 verbatim `examples` (short quoted user pushbacks, or named anti-patterns).

### `suggestions`
Three sub-arrays:
- **`claude_md_additions`** — concrete patches the user could paste into `~/.claude/CLAUDE.md`. Each `code` field MUST start with a `## H2` heading and contain ~2-4 sentences of body. The `why` field cites the corpus pattern that motivates it.
- **`features_to_try`** — Claude Code features (skills / hooks / parallel agents / headless mode / MCP / etc.) that map onto the user's existing patterns. `why` explains which pattern in *their* corpus this feature would replace or amplify.
- **`patterns_to_keep`** — things they already do that they should NOT change. Confirmation of validated behaviors.

### `horizon`
Forward-looking opportunities. Each card describes something the user could automate or scale up, given what they're already doing. `whats_possible` paints the picture; `how_to_try` gives the concrete first step. Don't propose generic AI futures — propose extensions of *their* current patterns.

### `fun_ending`
One surprising observation from the data. Pithy, specific, true. The kind of fact a peer reviewer would highlight after reading the corpus.

## Self-check before emitting

Before outputting JSON, verify:
- [ ] Every card has a `source` field.
- [ ] At least 5 cards across the whole output quote a verbatim phrase from the deep-read reports.
- [ ] No section has fewer than its `minItems` count.
- [ ] The `code` field in every `claude_md_additions` card starts with `## `.
- [ ] No emoji.
- [ ] Output is valid JSON (no trailing commas, no unescaped newlines inside strings).

Emit the JSON now.
