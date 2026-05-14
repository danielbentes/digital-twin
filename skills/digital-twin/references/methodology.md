# Digital Twin Methodology

The `digital-twin` skill mines the user's own Claude Code session logs to produce a behavioral profile and an installable subagent. This document is the reference for HOW that's done.

The methodology is 6 passes. Each pass has a purpose, an input, an output, and a "why this is hard" note explaining the design choice.

## Pass 1 — Setup (~2 min)

**Purpose:** Confirm the corpus is large enough to produce high-signal output and that the right human is being mined.

**Input:** `~/.claude/projects/` directory.

**Output:** Console summary. No files written.

**Why this is hard:** A corpus below ~500 user-typed prompts (after automated-wake filtering) produces noisy outputs. We warn early rather than burning ~$10 of agent time on a useless run.

**Checks:**
1. `~/.claude/projects/` exists and has ≥1 project subdirectory.
2. Total prompts across all jsonl files ≥ `--min-prompts-warn` (default 500).
3. Single-user machine assumption is verified by asking the user.
4. If >50k prompts, suggest `--sample` mode to bound cost.

## Pass 2 — Extract (~3 min)

**Purpose:** Normalize the raw session logs into 4 corpus files that downstream passes consume.

**Input:** All `*.jsonl` files under `~/.claude/projects/`.

**Output:**
- `corpus.jsonl` — prompt-bearing entries, one JSON object per line, preferring full `user`/`human` messages over truncated `last-prompt` cache rows only when the cache row is an exact or clear-prefix duplicate of the full message
- `first-prompts.jsonl` — first prompt of each session
- `human-first.jsonl` — long, high-signal real human first-prompts (auto-wakes excluded)
- `timestamped.jsonl` — prompts with valid timestamps (for temporal pass)
- `_summary.json` — file/prompt counts and per-project breakdown

**Why this is hard:** Session logs have at least 3 entry types that carry user text (`last-prompt`, `user`, sometimes `human`) and ~5 different content shapes (string, list of blocks, etc.). They also include automated wake payloads (Paperclip heartbeats, autonomous-loop wakes) that look like prompts but aren't human-typed. We strip those for `human-first.jsonl` but keep them in `corpus.jsonl` because they reveal automation patterns.

**Schema:** see `extraction-schema.md`.

## Pass 3 — Quantitative (~3 min)

**Purpose:** Produce the headline numbers that anchor every other claim. Human voice/style metrics use records marked `is_human_typed`; automation traffic remains available as orchestration evidence.

**Input:** `corpus.jsonl` + `timestamped.jsonl`.

**Output:**
- `numbers.json` / `numbers.md` — counts, vocab, slash-command frequency, language detection, source-type counts
- `temporal.json` / `temporal.md` — hour/day histograms, recovery cycles, drift

**Why this is hard:**
- **Stopword sets** must cover at least English + the 3-5 most common second languages, otherwise non-English speakers' vocabulary signals get drowned.
- **Recovery cycles** are computed per-session: walk forward looking for a pushback-first-word, then count turns until the next approval-first-word. Sessions that span multiple back-to-back pushbacks vs single recovery cycles must be distinguished.
- **Vocabulary drift** uses 25/75 quartile slicing on chronological order. Smaller slices increase noise; larger slices hide drift.

## Pass 4 — Deep sources (~5 sec, parallel)

**Purpose:** Mine sources outside the prompt corpus that both the deep-read agents and twin-spec extractor need: persistent memory files, plan documents, assistant↔user turn pairs, and (optionally) PR comments.

**Input:** `~/.claude/projects/*/memory/`, `~/.claude/plans/`, project-local `.decisions/`, GitHub PR comments.

**Output:**
- `memory-inventory.json` / `rules.md` — every memory file classified
- `plan-inventory.json` / `plans.md` — plan archetype distribution + drift
- `convergence-pairs.json` / `pushback-triggers.md` — convergence stats
- `pr-comments.json` / `pr-template.md` — PR comment structural patterns (optional)

**Why this is hard:**
- Memory files have YAML frontmatter that must be parsed correctly across all 4 types (`user`, `feedback`, `project`, `reference`).
- Plan files are scattered: `~/.claude/plans/`, per-project `.decisions/`, `docs/plans/`. Discovering them requires globbing multiple locations.
- The (assistant, user) pair construction is fragile — entries are stamped per-message, not per-turn, and assistant entries can span multiple JSON objects. We collapse to the last assistant text before each user reply.
- PR mining via `gh` is best-effort: the script must work cleanly when `gh` is missing or unauthenticated.

## Pass 5 — Qualitative agents (~20 min, parallel)

**Purpose:** Produce 6 deep reads that no quantitative pass could capture: how the user delegates, how they pick conventions, how they push back, how their plans are structured, etc.

**Input:** corpus files + numbers + temporal + deep-source outputs + the 6 templated prompts in `references/prompts/`.

**Output:** 6 markdown reports in `~/.claude/digital-twin/analysis/reports/`:
- `orchestration.md`
- `workflow.md`
- `quality.md`
- `encoded-rules.md`
- `planning-style.md`
- `failure-recovery.md`

**Why this is hard:**
- Each report would take ~15-25 minutes serially. Running 6 in parallel collapses that to ~20 min wall-clock.
- The prompts must be **self-contained** — each agent starts cold, so the prompt has to include enough context (quantitative facts, corpus paths, expected output format) that the agent doesn't need clarification.
- Each agent reads ~80k input tokens of corpus and produces ~12k output tokens of report. Cost per run is dominated by these 6 dispatches.
- Quoting verbatim prompts is mandatory — generic best-practice language from training data is the failure mode.

**Implementation:** the command dispatches these by reading each template, filling placeholders with values from `numbers.json`, `temporal.json`, and the Pass 4 deep-source outputs, then invoking 6 general-purpose Agents in a single message (parallel).

## Pass 5.5 — Profile insights (~3-10 min)

**Purpose:** Convert the 6 free-form reports and quantitative stats into structured card data for `PROFILE.md` and `PROFILE.html`.

**Input:** `analysis/reports/*.md` and the primary stats JSON files.

**Output:** 7 JSON files under `analysis/insights/`.

**Why this is hard:** The profile needs compact, readable insight cards, not raw report dumps. This extraction pass keeps profile rendering stable while preserving fallback behavior if the LLM step fails.

## Pass 5.6 — Behavioral twin spec (~3-10 min)

**Purpose:** Convert reports, insights, stats, and deep-source inventories into the compact operational contract used to render the replacement agent.

**Input:** `analysis/reports/*.md`, `analysis/insights/*.json`, primary stats JSON files, `memory-inventory.json`, `plan-inventory.json`, and `convergence-pairs.json`.

**Output:** `analysis/twin-spec.json`.

**Why this is hard:** A profile explains the user; an agent needs executable policy. The spec must deduplicate memory rules, separate biography from operating behavior, cite evidence for each durable rule, keep project-specific detail outside the always-loaded subagent prompt, and pass schema validation before synthesis treats it as complete.

## Pass 6 — Synthesize (~10 min)

**Purpose:** Fill the 3 templates (profile, subagent, CLAUDE.md patch) with all analysis outputs and write the final artifacts.

**Input:** All analysis JSON + all 6 agent reports + the 3 templates in `references/`.

**Output:**
- `~/.claude/digital-twin/PROFILE.md`
- `~/.claude/agents/twin.md`
- `~/.claude/digital-twin/CLAUDE-md-patch.md`
- `~/.claude/digital-twin/rules/*.md`
- `~/.claude/digital-twin/gotchas.md`
- `~/.claude/digital-twin/numbers.md`
- `~/.claude/digital-twin/_synthesis.json` (metadata)

**Why this is hard:**
- The profile templates use insights/cards. The subagent and rule files are driven primarily by `analysis/twin-spec.json`.
- If an agent report is missing (e.g., user ran a partial pipeline), the synthesize step must degrade gracefully — write `_pending_` rather than fail.
- If `twin-spec.json` is missing, the profile still renders but `twin.md` must carry an explicit incomplete-spec warning rather than pretending to be a replacement twin.
- Unfilled placeholders should be visible to the user, not silently dropped. `synthesize.py` prints the list of any `_TBD_KEY_` markers at the end.

---

## Roadmap (v0.2 → v1.0)

| Version | Adds |
| --- | --- |
| v0.2 | Behavioral Twin v1 — `twin-spec.json`, compact subagent, generated CLAUDE rules, deterministic eval harness |
| v0.3 | Cursor / Aider / Codex CLI log adapters (mine non-Claude-Code corpora) |
| v0.4 | Team profiles — mine multiple users' corpora, produce shared "team operating style" |
| v0.5 | Self-updating twin — `pushback-detector.py` watches live sessions and proposes new memory rules |
| v1.0 | Full test coverage + CI + marketplace publication + multi-user validation |

---

## Validation

The methodology was first validated on a single power-user corpus (12,228 prompts, 39 projects, 18 months of usage). Acceptance criteria for v1.0 across beta users:

- ≥80% of beta users say the twin "sounds like me" on blind A/B prompt comparisons.
- ≥70% of known per-user pushback triggers are caught by the twin's NEVER list.
- ≥90% of v1.0 installations complete the 60-90 minute first run without errors.

---

## Privacy invariants

The methodology MUST hold these invariants on every run:

1. **No network calls from non-LLM local Python/shell passes** except optional `gh api` for PR mining. LLM-bound passes use the user's existing Claude Code auth and are called out explicitly; API-key SDK fallback must be opt-in.
2. **No telemetry** — the skill never reports back to any author.
3. **Local-only writes** — outputs land in `~/.claude/digital-twin/` and `~/.claude/agents/`. Nothing under `~/.claude/projects/` is modified.
4. **No auto-memory writes** — even the self-updating twin (v0.4+) writes proposals to a review queue, never directly to memory files.

If a future pass needs to upload anything anywhere, the skill must explicitly ask the user with full provenance ("this will upload X to Y; the data contains Z").
