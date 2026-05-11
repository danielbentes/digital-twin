# digital-twin

> A Claude Code plugin that mines your own session logs to build a digital twin: a profile of how you actually work, a sub-agent that imitates you, and a CLAUDE.md patch you can drop into any new project.

Your session logs never leave your machine. The local Python pipeline (extract → quantitative → temporal → memory/plan/convergence inventories → synthesize) reads from `~/.claude/projects/` and writes to `~/.claude/digital-twin/`. Two LLM steps in the pipeline use your existing Claude Code auth (no third-party services, no Anthropic API key): Phase 4 dispatches 6 parallel deep-read agents and Phase 4.5 makes one structured-extraction call. No telemetry.

---

## What it does

The plugin walks `~/.claude/projects/*/*.jsonl` (every Claude Code session you've ever had) and produces six artifacts:

| Artifact | What it is |
|---|---|
| `PROFILE.md` | An insights-style report: how you orchestrate, where you push back, what plans you write, what rules you've encoded. Includes ASCII charts. |
| `PROFILE.html` | The same report with inline SVG charts. Self-contained — open in any browser. |
| `~/.claude/agents/twin.md` | A sub-agent that imitates you: same voice, same rules, same workflows. Invocable as `@twin` (or via the `Agent` tool). |
| `CLAUDE-md-patch.md` | A patch you can append to any project's `CLAUDE.md` to give Claude Code your operating defaults. |
| `gotchas.md` | Seed list of pushback patterns from your own corpus. Editable. |
| `numbers.md` | Canonical metrics — source of truth for everything else. |

It also runs an **opt-in self-update loop**: every so often, run `/digital-twin:propose-rules` and the plugin will queue candidate memory rules drafted from pushbacks the detector saw but you haven't encoded yet. You approve each one explicitly — nothing is auto-written.

---

## Install

### From this repo (local development)

```bash
git clone https://github.com/danielbentes/digital-twin ~/code/digital-twin
claude --plugin-dir ~/code/digital-twin
```

Or, once published to a marketplace:

```bash
claude plugin install danielbentes/digital-twin
```

After install, invoke any of the slash commands:

```
/digital-twin:init           # first-time build (local pipeline ~20 sec; 2 LLM phases dominate wall-clock)
/digital-twin:update         # refresh against new logs (re-runs the local pipeline + extraction)
/digital-twin:status         # show what's known about you so far
/digital-twin:propose-rules  # review pending pushback-derived rule proposals
```

---

## Quickstart (manual, without the slash command)

If you'd rather drive the pipeline yourself:

```bash
SKILL=~/code/digital-twin/skills/digital-twin
OUT=/tmp/dt-run

# 1. Extract corpus from all session logs
python3 $SKILL/scripts/extract-corpus.py --out $OUT

# 2. Quantitative pass (vocab, slash share, languages, ...)
python3 $SKILL/scripts/quantitative.py \
  --corpus $OUT/corpus.jsonl \
  --out-json $OUT/numbers.json --out-md $OUT/numbers.md

# 3. Temporal pass (hour/day histogram, recovery cycles, drift)
python3 $SKILL/scripts/temporal.py \
  --timestamped $OUT/timestamped.jsonl \
  --out-json $OUT/temporal.json --out-md $OUT/temporal.md \
  --tz-offset-hours 2   # adjust to your local UTC offset

# 4. Memory + plan inventories
python3 $SKILL/scripts/memory-inventory.py \
  --out-json $OUT/memory-inventory.json --out-md $OUT/rules.md
python3 $SKILL/scripts/plan-inventory.py \
  --out-json $OUT/plan-inventory.json --out-md $OUT/plans.md \
  --search-dir ~/code   # add directories where you keep .decisions/ folders

# 5. Convergence analysis (assistant-turn → user-reply pairs)
python3 $SKILL/scripts/assistant-turn-mining.py \
  --out-json $OUT/convergence-pairs.json \
  --out-md $OUT/pushback-triggers.md

# 6. (Optional) PR comment style — needs `gh` CLI authenticated
$SKILL/scripts/pr-comment-mining.sh --out $OUT/pr-comments.json

# 7. Synthesize → PROFILE.md, PROFILE.html, twin.md, CLAUDE-md-patch.md
mkdir -p $OUT/reports
python3 $SKILL/scripts/synthesize.py \
  --analysis $OUT --reports $OUT/reports \
  --out $OUT/out --agents-dir $OUT/agents \
  --user-name "$USER"

open $OUT/out/PROFILE.html  # macOS — or xdg-open on Linux
```

The qualitative deep-read phase (6 parallel agents producing 1500-2500 word reports) plus Phase 4.5 (the structured-extraction pass that turns those reports into card data) are what `/digital-twin:init` orchestrates and are **not** included in the manual pipeline above. Without them, `synthesize.py` runs at Tier 2 (rule-based card content scraped from numbers + reports if any) or Tier 3 (`_pending_` markers if neither). The synthesized numbers and charts work at all three tiers; only the narrative card depth differs.

---

## Self-updating loop (Phase 4)

The plugin includes a **pushback detector** that watches `(assistant-turn, user-reply)` pairs incrementally. When it sees a pushback that isn't already covered by an existing memory rule, it drafts a candidate rule and queues it at `~/.claude/digital-twin/proposed-rules/`.

```bash
# Run the detector manually (incremental — only new sessions since last run)
python3 ~/code/digital-twin/skills/digital-twin/scripts/pushback-detector.py

# Review pending proposals interactively
/digital-twin:propose-rules
```

The detector **never writes to memory directly**. Every approval is explicit; rejected proposals move to an `archive/` subdirectory for audit.

You can wire the detector to a Claude Code `PostToolUse` hook so it runs after every turn — see `examples/hook-config.json` for a sample (not auto-installed).

---

## What you'll learn

Sample insights the plugin surfaces from a real corpus (~20k prompts):

- **Convergence shape** — what % of your replies are first-word approvals (`go`, `ship`) vs explicit pushback (`stop`, `wait`) vs implicit pushback (long replies with `actually`/`but`/`instead` markers).
- **Recovery cost** — how many turns it takes you to return to approval after a pushback (median and p90).
- **Plan rigor over time** — does your out-of-scope adoption rise, fall, or stay flat as you write more plans?
- **Vocabulary drift** — which steering verbs are rising vs fading in your most recent quarter of work.
- **Top encoded rules** — every feedback-type memory file across all your projects, deduplicated and grouped.

The HTML version embeds inline SVG charts: hour-of-day bar chart with peak hour highlighted, day-of-week histogram, convergence donut, and plan-rigor drift comparison. The encoded-rules section renders each memory rule as a card grouped by project, with Why and How-to-apply sections parsed out of the rule body.

---

## Privacy

- **Your session logs never leave your machine.** The local Python pipeline reads from `~/.claude/projects/` and writes to `~/.claude/digital-twin/` + `~/.claude/agents/twin.md`. The corpus jsonls themselves are never sent over the network.
- **Two LLM steps go through your existing Claude Code auth:** Phase 4 dispatches 6 deep-read agents via the Agent tool, Phase 4.5 makes one structured-extraction call via `claude -p`. Both ride your existing auth — no third-party services, no Anthropic API key required.
- **Optional `pr-comment-mining.sh`** calls `gh` (your own CLI) and skips gracefully if unauthenticated.
- **No telemetry. No analytics. No phone-home.**

Your `private/` directory in this repo (if present) is gitignored — personal corpora and intermediate analysis live there.

---

## Customizing the twin

The synthesized `twin.md` sub-agent has hardcoded defaults for sections the deep-read agents would normally populate (operating model, workflow A/B/C/D, anti-patterns, etc.). To override them with your own corpus-specific phrasing, run `/digital-twin:init`. The 6 deep-read agents write free-form narrative to `analysis/reports/`, then Phase 4.5 (`extract-insights.py`) distills those into 7 structured JSON files in `analysis/insights/`. The synthesizer reads the JSON directly and renders cards in PROFILE.html. If extraction fails or the reports aren't there, it falls through to rule-based content (Tier 2) or `_pending_` placeholders (Tier 3) — the pipeline never hard-fails.

The CLAUDE.md patch is intended to be edited before you commit it — it's a starting point, not a finished doc.

---

## FAQ

**Q: How much does `/digital-twin:init` cost?**
A: ~$5-9 for a first run. Breakdown: 6 deep-read agents × ~80k input + ~12k output ≈ 540k tokens (~$4-8 Sonnet 4.6) plus one ~$0.50-1 extraction call. `update` skips the agents by default and reuses cached reports, so it's ~$1.

**Q: How long does `/digital-twin:init` take?**
A: The local pipeline (extract → quantitative → temporal → memory/plan/convergence → synthesize) runs in **~20 seconds** on a 10k-session corpus. The two LLM-bound phases dominate everything else: Phase 4 (6 parallel deep-read agents) is variable based on model latency, and Phase 4.5 (one Sonnet extraction call) measured 3-10 minutes in testing. There's no useful fixed total — depends on agent dispatch.

**Q: Can I run it without the deep-read agents?**
A: Yes — run the manual pipeline above through step 7. You get a profile with the analytical scaffolding, charts, and rule-based card content (Tier 2). Run Phase 4 + 4.5 later to upgrade to Tier 1 (rich, evidence-quoted cards).

**Q: Does it work with non-English session content?**
A: Yes — the corpus extractor is encoding-agnostic. The quantitative pass detects dominant non-English language (Norwegian, German, Spanish, French currently). Heuristics will degrade gracefully on other languages.

**Q: Is the pushback detector active by default?**
A: No. You run it manually or wire it to a hook (sample in `examples/hook-config.json`). The detector itself is incremental and stateful — it tracks the byte offset of the last line it processed in each session file.

**Q: Can I share my `PROFILE.html`?**
A: Yes, but it contains your project names, top steering verbs, and possibly memory-file content quoted verbatim. Review before sharing publicly. The synthesizer does not anonymize.

---

## Roadmap

- **v0.2 (current, unreleased)** — Phase 4.5 structured-extraction pass; three-tier card sourcing; encoded-rule cards parser; polished SVG charts. See `CHANGELOG.md` for the full list.
- **v0.3** — Cursor adapter (Cursor's chat history has similar structure); split `synthesize.py` into smaller modules.
- **v0.4** — Marketplace publication; PostToolUse hook bundled (currently sample-only).
- **v1.0** — Comparison mode (you vs another team's profile) and team-level twin synthesis.

---

## License

MIT — see [LICENSE](LICENSE).
