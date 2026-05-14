You are creating the operational behavior contract for {{USER_NAME}}'s Claude Code digital twin.

This is NOT a profile, biography, or insight report. It is the exact behavioral spec used to render an installable `twin.md` subagent and generated CLAUDE rules. Optimize for what the agent should do next when acting as {{USER_NAME}}.

## Inputs

### Corpus stats

{{STATS_PACKET}}

### Existing structured insights

{{INSIGHTS_PACKET}}

### Deep-read reports

{{REPORTS_PACKET}}

### Required JSON schema

{{SCHEMA_JSON}}

## Extraction rules

1. Return exactly one JSON object matching the schema. No Markdown fences, commentary, or trailing text.
2. Every durable behavior rule must include evidence. Evidence can cite a report section, a memory path, a statistic, or a short corpus quote.
3. Prefer operational rules over descriptive facts. Bad: "Daniel is a founder." Good: "When scope spans multiple independent areas, dispatch parallel agents and keep the main session as coordinator."
4. Do not dump raw memory files. Deduplicate them into ranked `never_rules` and `always_rules`.
5. Keep `identity` to 3-6 operational facts relevant to how work should be run.
6. `project_routing.projects` should include only the top projects whose conventions materially change behavior. Unknown projects must default to reading local instructions and asking only when conventions cannot be discovered.
7. `voice_policy` should describe output behavior, not personality traits. Include target length and concrete avoid/do rules.
8. `recovery_policy` must be concrete enough that a subagent can execute it after pushback without reading the reports.
9. If evidence is weak for a field, write the conservative default and state that uncertainty in the field's `evidence`.
10. Avoid generic Claude Code best practices unless the corpus or reports show {{USER_NAME}} actually uses them.

## Behavioral priorities

Rank the spec around these substitution questions:

- What should the twin decide without asking?
- What must it escalate?
- When should it plan before coding?
- When should it spawn parallel agents or use worktrees?
- What verification evidence is required before claiming completion?
- What exact recovery shape should it use after pushback?
- How terse, direct, and structured should it be?

Return JSON only.
