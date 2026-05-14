# digital-twin

> A Claude Code plugin that mines your own session logs to build a digital twin: a profile of how you actually work, a sub-agent that imitates you, and a CLAUDE.md patch you can drop into any new project.

Local extraction/statistics/rendering stay on your machine. The LLM-bound phases use your existing Claude Code auth and can send corpus-derived evidence to Claude: deep-read agents, profile-insight extraction, and compact behavioral `twin-spec.json` extraction. No plugin telemetry.

---

## What it does

The plugin walks `~/.claude/projects/*/*.jsonl` (every Claude Code session you've ever had) and produces six artifacts:

| Artifact | What it is |
|---|---|
| `PROFILE.md` | An insights-style report: how you orchestrate, where you push back, what plans you write, what rules you've encoded. Includes ASCII charts. |
| `PROFILE.html` | The same report with inline SVG charts. Self-contained — open in any browser. |
| `~/.claude/agents/twin.md` | A compact operational subagent rendered from `analysis/twin-spec.json`. Invocable as `@twin` (or via the `Agent` tool). |
| `rules/*.md` | Generated CLAUDE rule files for preferences, workflows, verification, and recovery. |
| `CLAUDE-md-patch.md` | A short install guide that imports or symlinks the generated rules. |
| `gotchas.md` | Seed list of pushback patterns from your own corpus. Editable. |
| `numbers.md` | Canonical metrics — source of truth for everything else. |

It also runs an **opt-in self-update loop**: every so often, run `/digital-twin:propose-rules` and the plugin will queue candidate memory rules drafted from pushbacks the detector saw but you haven't encoded yet. You approve each one explicitly — nothing is auto-written.

---

## Install

### From the marketplace (recommended)

This repo is its own single-plugin marketplace — one `add` + one `install`:

```
/plugin marketplace add danielbentes/digital-twin
/plugin install digital-twin@digital-twin
```

The first `digital-twin` is the plugin name; the `@digital-twin` is the marketplace name. They happen to be the same because this repo is both the plugin and its catalog.

### From a local checkout (for development)

```bash
git clone https://github.com/danielbentes/digital-twin ~/code/digital-twin
claude --plugin-dir ~/code/digital-twin
```

Useful if you want to edit the skill while running it.

### Verify the install

```
/plugin list
```

You should see `digital-twin` enabled. After install, invoke any of the slash commands:

```
/digital-twin:init           # first-time build (local pipeline ~20 sec; 2 LLM phases dominate wall-clock)
/digital-twin:update         # refresh against new logs (re-runs the local pipeline + extraction)
/digital-twin:status         # show what's known about you so far
/digital-twin:propose-rules  # review pending pushback-derived rule proposals
```

### Update

When a new version ships, refresh and reinstall:

```
/plugin marketplace update digital-twin
/plugin install digital-twin@digital-twin
```

Or enable auto-update in your Claude Code settings.

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
$SKILL/scripts/pr-comment-mining.sh --out-json $OUT/pr-comments.json

# 7. Behavioral twin spec (default for replacement-agent output).
# If Phase 5 reports or Phase 5.5 insights exist, this writes twin-spec.json.
# If you are running this local-only quickstart before deep-read reports exist,
# --allow-empty keeps the profile pipeline moving and synthesis emits a degraded
# twin.md warning instead of pretending the replacement agent is complete.
mkdir -p $OUT/reports
python3 $SKILL/scripts/extract-twin-spec.py \
  --analysis-dir $OUT --reports-dir $OUT/reports \
  --out-json $OUT/twin-spec.json --user-name "$USER" \
  --allow-empty

# 8. Synthesize → PROFILE.md, PROFILE.html, twin.md, rules/, CLAUDE-md-patch.md
python3 $SKILL/scripts/synthesize.py \
  --analysis $OUT --reports $OUT/reports \
  --out $OUT/out --agents-dir $OUT/agents \
  --user-name "$USER"

open $OUT/out/PROFILE.html  # macOS — or xdg-open on Linux
```

The qualitative deep-read phase (6 parallel agents producing 1500-2500 word reports), Phase 5.5 (profile-card extraction), and Phase 5.6 (behavioral twin-spec extraction) are what `/digital-twin:init` orchestrates. Without insights, `synthesize.py` still renders profile charts via Tier 2/3 fallbacks. Without `twin-spec.json`, it writes an explicitly degraded `twin.md` warning instead of pretending the agent can replace you.

---

## Self-updating loop

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

- **Local phases stay local.** The Python extraction/statistics/rendering scripts read from `~/.claude/projects/` and write to `~/.claude/digital-twin/` + `~/.claude/agents/twin.md`; they do not upload files on their own.
- **LLM phases send corpus-derived evidence to Claude.** Phase 5 dispatches 6 deep-read agents, Phase 5.5 makes one profile-insights extraction call via `claude -p`, and Phase 5.6 makes one behavioral-spec extraction call via `claude -p`. These use your existing Claude Code auth and can include selected prompts, reports, quotes, stats, and memory-derived evidence. `extract-insights.py` only uses the Anthropic SDK/API-key fallback when you explicitly pass `--allow-sdk-fallback`.
- **Generated HTML is self-contained.** `PROFILE.html` uses inline CSS/SVG and local system fonts only.
- **Optional `pr-comment-mining.sh`** calls `gh` (your own CLI) and skips gracefully if unauthenticated.
- **No plugin telemetry. No analytics. No phone-home outside the explicit Claude/GitHub calls above.**

Your `private/` directory in this repo (if present) is gitignored — personal corpora and intermediate analysis live there.

---

## Customizing the twin

The synthesized `twin.md` sub-agent is rendered from `analysis/twin-spec.json`, not from a raw memory dump. The 6 deep-read agents write free-form narrative to `analysis/reports/`; Phase 5.5 (`extract-insights.py`) distills profile cards into `analysis/insights/`; Phase 5.6 (`extract-twin-spec.py`) distills operational behavior into `analysis/twin-spec.json`. `synthesize.py` also emits `rules/preferences.md`, `rules/workflows.md`, `rules/verification.md`, and `rules/recovery.md` for CLAUDE.md installation.

The CLAUDE.md patch is intended to be edited before you commit it — it's a starting point, not a finished doc.

---

## FAQ

**Q: How much does `/digital-twin:init` cost?**
A: ~$5-9 for a first run. Breakdown: 6 deep-read agents × ~80k input + ~12k output ≈ 540k tokens (~$4-8 Sonnet) plus two ~$0.50-1 extraction calls. `update` skips the agents by default when cached reports are reused, so it's roughly the two extraction calls.

**Q: How long does `/digital-twin:init` take?**
A: The local pipeline (extract → quantitative → temporal → memory/plan/convergence → synthesize) runs in **~20 seconds** on a 10k-session corpus. The LLM-bound phases dominate everything else: Phase 5 (6 parallel deep-read agents) is variable based on model latency, Phase 5.5 extracts profile insights, and Phase 5.6 extracts the behavioral twin spec. There's no useful fixed total — depends on agent dispatch.

**Q: Can I run it without the deep-read agents?**
A: Yes — run the manual pipeline above through step 6, skip step 7, then run step 8. You get a profile with the analytical scaffolding, charts, and rule-based card content (Tier 2) plus an explicitly degraded twin warning. Run Phase 5 + 5.5 + 5.6 later to generate the replacement-agent spec.

**Q: Does it work with non-English session content?**
A: Yes — the corpus extractor is encoding-agnostic. The quantitative pass detects dominant non-English language (Norwegian, German, Spanish, French currently). Heuristics will degrade gracefully on other languages.

**Q: Is the pushback detector active by default?**
A: No. You run it manually or wire it to a hook (sample in `examples/hook-config.json`). The detector itself is incremental and stateful — it tracks the byte offset of the last line it processed in each session file.

**Q: Can I share my `PROFILE.html`?**
A: Yes, but it contains your project names, top steering verbs, and possibly memory-file content quoted verbatim. Review before sharing publicly. The synthesizer does not anonymize.

---

## Roadmap

- **v0.2 (current, unreleased)** — Behavioral Twin v1: profile extraction, `twin-spec.json`, compact subagent rendering, generated CLAUDE rules, deterministic eval harness, three-tier profile card sourcing, encoded-rule cards parser, polished SVG charts.
- **v0.3** — Cursor adapter (Cursor's chat history has similar structure); split `synthesize.py` into smaller modules.
- **v0.4** — Marketplace publication; PostToolUse hook bundled (currently sample-only).
- **v1.0** — Comparison mode (you vs another team's profile) and team-level twin synthesis.

---

## License

MIT — see [LICENSE](LICENSE).
