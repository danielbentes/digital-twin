from __future__ import annotations

import argparse
import datetime as dt
import getpass
import os
import sys
from pathlib import Path

from twin_spec_validation import validate_twin_spec

from .output_writing import write_final_outputs, write_rules_files
from .profile_construction import (
    _esc,
    build_claude_md_additions,
    build_claude_md_items,
    build_features_cards,
    build_features_to_try,
    build_friction,
    build_friction_cards,
    build_fun_finding,
    build_fun_parts,
    build_headline_summary,
    build_horizon_cards,
    build_interaction_style,
    build_on_the_horizon,
    build_patterns_cards,
    build_project_area_dicts,
    build_project_areas,
    build_stats_row,
    build_usage_patterns_to_keep,
    build_what_works,
    build_what_works_cards,
)
from .profile_formatting import (
    build_always_list,
    build_never_list,
    build_canonical_numbers,
    build_encoded_rules_section,
    build_identity_section,
    build_project_glossary,
    build_top_encoded_rules_terse,
    build_top_words_table,
    build_top_words_table_html,
    fmt_big_wins,
    fmt_claude_md_items,
    fmt_encoded_rules_cards,
    fmt_features,
    fmt_friction,
    fmt_horizon,
    fmt_md_cards_titled,
    fmt_md_claude_md_additions,
    fmt_md_features,
    fmt_md_friction_cards,
    fmt_md_horizon,
    fmt_md_patterns,
    fmt_md_project_areas,
    fmt_patterns,
    fmt_project_areas,
    fmt_stats_row,
    load_insights,
    html_to_text,
)
from .shared import (
    PLACEHOLDER_RE,
    PLUGIN_ROOT,
    TWIN_SPEC_SCHEMA_PATH,
    charts,
    fill,
    html_safe_context,
    load_json,
    load_text,
    md_to_html,
    sanitize_html_fragment,
    sanitize_user_name,
)
from .spec_core import (
    CURRENT_SCHEMA_VERSION,
    build_degraded_twin_spec,
    migrate_twin_spec,
)
from .twin_rendering import render_operating_model, render_twin_context


def hour_dict_to_list(d: dict | list | None) -> list[int]:
    if not d:
        return [0] * 24
    if isinstance(d, list):
        return list(d) + [0] * (24 - len(d))
    out = [0] * 24
    for k, v in d.items():
        try:
            i = int(k)
            if 0 <= i < 24:
                out[i] = int(v)
        except (TypeError, ValueError):
            continue
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--analysis", default=os.path.expanduser("~/.claude/digital-twin/analysis"))
    ap.add_argument("--reports", default=os.path.expanduser("~/.claude/digital-twin/analysis/reports"))
    ap.add_argument("--out", default=os.path.expanduser("~/.claude/digital-twin"))
    ap.add_argument("--agents-dir", default=os.path.expanduser("~/.claude/agents"))
    ap.add_argument("--templates", default=str(PLUGIN_ROOT / "references"))
    ap.add_argument("--user-name", default=os.environ.get("DIGITAL_TWIN_USER_NAME", getpass.getuser()))
    ap.add_argument("--profile-version", default="v0.1")
    ap.add_argument("--target-twin-reply-len", type=int, default=600)
    ap.add_argument(
        "--strict-substitution",
        action="store_true",
        help=(
            "Refuse to backfill missing substitution sections from historical "
            "v0.3 specs. When set, a legacy spec without constitution / "
            "substitution_contract / trust_policy / agent_supervision_policy "
            "produces a degraded twin instead of a compatibility-derived one."
        ),
    )
    args = ap.parse_args()
    args.user_name = sanitize_user_name(args.user_name)

    analysis = Path(args.analysis).expanduser()
    reports = Path(args.reports).expanduser()
    out = Path(args.out).expanduser()
    agents_dir = Path(args.agents_dir).expanduser()
    templates = Path(args.templates).expanduser()

    out.mkdir(parents=True, exist_ok=True)
    agents_dir.mkdir(parents=True, exist_ok=True)

    numbers = load_json(analysis / "numbers.json", default={}) or {}
    corpus_summary = (
        load_json(analysis.parent / "corpora" / "_summary.json", default=None)
        or load_json(analysis / "_summary.json", default={})
        or {}
    )
    temporal = load_json(analysis / "temporal.json", default={}) or {}
    memory = load_json(analysis / "memory-inventory.json", default={}) or {}
    plan_inv = load_json(analysis / "plan-inventory.json", default={}) or {}
    convergence = load_json(analysis / "convergence-pairs.json", default={}) or {}
    pr_stats = load_json(analysis / "pr-comments.json", default={}) or {}
    twin_spec_path = analysis / "twin-spec.json"
    twin_spec = load_json(twin_spec_path, default=None)
    twin_spec_complete = isinstance(twin_spec, dict) and bool(twin_spec)
    twin_spec_compat_defaults = False
    if twin_spec_complete:
        migrated_spec, twin_spec_compat_defaults, migration_error = migrate_twin_spec(
            twin_spec,
            args.user_name,
            strict_substitution=args.strict_substitution,
        )
        if migration_error:
            reason = f"{twin_spec_path} {migration_error}"
            print(f"WARN: {reason}", file=sys.stderr)
            twin_spec = build_degraded_twin_spec(args.user_name, reason=reason)
            twin_spec_complete = False
            twin_spec_compat_defaults = False
        else:
            # The migration chain, not the renderer, owns compatibility. Only
            # its output is allowed to reach schema validation.
            twin_spec = migrated_spec
            twin_spec_errors = validate_twin_spec(
                twin_spec,
                TWIN_SPEC_SCHEMA_PATH,
                expected_version=CURRENT_SCHEMA_VERSION,
            )
            if twin_spec_errors:
                twin_spec_complete = False
                reason = (
                    f"{twin_spec_path} failed schema validation: "
                    + "; ".join(twin_spec_errors[:5])
                )
                print(f"WARN: {reason}", file=sys.stderr)
                twin_spec = build_degraded_twin_spec(args.user_name, reason=reason)
                twin_spec_compat_defaults = False
    else:
        reason = f"{twin_spec_path} missing"
        print(
            "WARN: analysis/twin-spec.json missing; writing degraded twin agent",
            file=sys.stderr,
        )
        twin_spec = build_degraded_twin_spec(args.user_name, reason=reason)
        twin_spec_compat_defaults = False

    orchestration_report = load_text(reports / "orchestration.md")
    workflow_report = load_text(reports / "workflow.md")
    quality_report = load_text(reports / "quality.md")
    encoded_rules_report = load_text(reports / "encoded-rules.md")

    n_session_files = numbers.get("n_session_files") or corpus_summary.get("n_session_files") or "?"
    date_range = "?"
    if temporal.get("date_range"):
        d = temporal["date_range"]
        date_range = f"{d['start'][:10]} → {d['end'][:10]}"

    # Sections
    project_glossary_md = build_project_glossary(memory, numbers)
    identity_section = build_identity_section(memory)
    encoded_rules_section = build_encoded_rules_section(memory)
    encoded_rules_cards_html = fmt_encoded_rules_cards(memory)
    top_encoded_terse = build_top_encoded_rules_terse(memory, top_n=10)
    canonical = build_canonical_numbers(numbers, temporal, plan_inv)
    never_list = build_never_list(convergence, encoded_rules_report, quality_report)
    always_list = build_always_list(convergence, workflow_report)

    # ---- Three-tier card sourcing ----
    # Tier 1: load extracted insights JSON (from extract-insights.py / Phase 5.5)
    # Tier 2: rule-based builders (numbers + reports → cards)
    # Tier 3: no reports either → cards say _pending_
    insights = load_insights(analysis / "insights")
    tier = 1 if insights else (2 if any(r for r in (orchestration_report, workflow_report, quality_report) if r) else 3)
    print(f"insights tier: {tier}", file=sys.stderr)

    # Default intros (Tier 2/3); overridden by Tier 1 if insights JSON has them.
    big_wins_intro = (
        f"Patterns that compound across {numbers.get('n_prompts', 0):,} prompts — "
        "keep them; they're load-bearing."
    )
    friction_intro = (
        "Where friction shows up most often. Each pattern is a candidate for an "
        "encoded memory rule."
    )
    horizon_intro = (
        "Forward-looking opportunities — extensions of patterns you already run."
    )

    if insights:
        # Tier 1 — drive everything off the JSON
        project_area_items = insights.get("project_areas") or []
        big_wins_cards = (insights.get("big_wins") or {}).get("cards") or []
        big_wins_intro = (insights.get("big_wins") or {}).get("intro") or big_wins_intro
        friction_card_list = (insights.get("friction") or {}).get("cards") or []
        friction_intro = (insights.get("friction") or {}).get("intro") or friction_intro
        sugg = insights.get("suggestions") or {}
        claude_md_card_items = sugg.get("claude_md_additions") or []
        features_card_list = sugg.get("features_to_try") or []
        patterns_card_list = sugg.get("patterns_to_keep") or []
        horizon_card_list = (insights.get("horizon") or {}).get("cards") or []
        horizon_intro = (insights.get("horizon") or {}).get("intro") or horizon_intro
        istyle = insights.get("interaction_style") or {}
        interaction_narrative_html = sanitize_html_fragment(istyle.get("narrative_html") or "")
        key_pattern_text = istyle.get("key_pattern") or ""
        fun_ending = insights.get("fun_ending") or {}
        fun_headline = fun_ending.get("headline") or ""
        fun_detail = fun_ending.get("detail") or ""
        # Plaintext (markdown) versions for PROFILE.md
        what_works_md = fmt_md_cards_titled(big_wins_cards, body_key="description")
        friction_md = fmt_md_friction_cards(friction_card_list)
        claude_md_md = fmt_md_claude_md_additions(claude_md_card_items)
        features_md = fmt_md_features(features_card_list)
        patterns_md = fmt_md_patterns(patterns_card_list)
        horizon_md = fmt_md_horizon(horizon_card_list)
        project_areas_md = fmt_md_project_areas(project_area_items)
        headline_md = html_to_text(interaction_narrative_html) or ""
        fun_md = f"**{fun_headline}**\n\n{fun_detail}"
    else:
        # Tier 2 / Tier 3 — rule-based builders
        project_area_items = build_project_area_dicts(numbers, memory, top_n=5)
        big_wins_cards = build_what_works_cards(convergence, numbers, plan_inv, workflow_report)
        friction_card_list = build_friction_cards(convergence, numbers, temporal, quality_report)
        claude_md_card_items = build_claude_md_items(convergence, numbers, memory)
        features_card_list = build_features_cards(numbers, plan_inv, memory, convergence)
        patterns_card_list = build_patterns_cards(workflow_report, plan_inv, convergence)
        horizon_card_list = build_horizon_cards(plan_inv, convergence, numbers)
        interaction_narrative_html, key_pattern_text = build_interaction_style(
            convergence, numbers, temporal, memory
        )
        fun_headline, fun_detail = build_fun_parts(numbers, temporal, convergence, memory)
        # Plaintext fallbacks use the existing narrative builders
        what_works_md = build_what_works(convergence, numbers, plan_inv, workflow_report)
        friction_md = build_friction(convergence, numbers, temporal, quality_report)
        claude_md_md = build_claude_md_additions(convergence, numbers, memory)
        features_md = build_features_to_try(numbers, plan_inv, memory, convergence)
        patterns_md = build_usage_patterns_to_keep(workflow_report, plan_inv, convergence)
        horizon_md = build_on_the_horizon(plan_inv, convergence, numbers)
        project_areas_md = build_project_areas(numbers, memory, top_n=5)
        headline_md = build_headline_summary(numbers, temporal, memory, convergence)
        fun_md = build_fun_finding(numbers, temporal, convergence, memory)

    # Always computed quantitatively (Tier doesn't matter):
    stats_row_items = build_stats_row(numbers, temporal, memory, convergence)

    # Visualizations
    hour_list = hour_dict_to_list(temporal.get("hour_histogram"))
    by_day = temporal.get("dow_histogram") or {}
    counts = convergence.get("counts", {})
    top_app = numbers.get("top_approval_words") or []
    top_pb = numbers.get("top_pushback_words") or []
    drift = plan_inv.get("drift")
    p90 = numbers.get("p90_prompt_length_chars") or 0
    median = numbers.get("median_prompt_length_chars") or 0

    hour_ascii = charts.hour_heatmap_ascii(hour_list)
    hour_svg = charts.hour_heatmap_svg(hour_list, peak_hour=temporal.get("peak_hour"))
    day_ascii = charts.day_histogram_ascii(by_day)
    day_svg = charts.day_histogram_svg(by_day, peak_day=temporal.get("peak_day"))
    conv_ascii = charts.convergence_bars_ascii(counts)
    conv_svg = charts.convergence_donut_svg(counts)
    app_bars_ascii = charts.word_bars_ascii(top_app, limit=10)
    app_bars_svg = charts.word_bars_svg(top_app, limit=10, color=charts.PAL["approval"], title="Top approval first-words")
    pb_bars_ascii = charts.word_bars_ascii(top_pb, limit=10)
    pb_bars_svg = charts.word_bars_svg(top_pb, limit=10, color=charts.PAL["explicit"], title="Top pushback first-words")
    drift_ascii = charts.drift_chart_ascii(drift)
    drift_svg = charts.drift_chart_svg(drift)
    prompt_len_svg = charts.percentile_bar_svg(median, p90) if (median or p90) else ""

    rec = temporal.get("recovery_cycles", {})
    feedback_count = sum(1 for e in memory.get("entries", []) if e.get("type") == "feedback")

    generated_date = dt.date.today().isoformat()
    generated_rule_files = write_rules_files(out, twin_spec, generated_date)

    ctx = {
        "USER_NAME": args.user_name,
        "GENERATED_DATE": generated_date,
        "PROFILE_VERSION": args.profile_version,
        "TWIN_VERSION": args.profile_version,
        "PROMPT_COUNT": f"{numbers.get('n_prompts', 0):,}",
        "N_SESSIONS": str(n_session_files),
        "N_PROJECTS": str(numbers.get("n_projects", 0)),
        "N_SESSION_FILES": str(n_session_files),
        "DATE_RANGE": date_range,
        "AVG_PROMPT_LEN": str(numbers.get("avg_prompt_length_chars", "?")),
        "MEDIAN_PROMPT_LEN": str(numbers.get("median_prompt_length_chars", "?")),
        "SLASH_SHARE_PCT": str(numbers.get("slash_share_pct", "?")),
        "N_APPROVALS": f"{numbers.get('approval_count', 0):,}",
        "N_PUSHBACKS": f"{numbers.get('pushback_count', 0):,}",
        "DOMINANT_LANGUAGE": numbers.get("dominant_second_language") or "none detected",
        "PEAK_HOUR": str(temporal.get("peak_hour", "?")),
        "PEAK_DAY": str(temporal.get("peak_day", "?")),
        "TZ_OFFSET": str(temporal.get("tz_offset_hours", 0)),
        "N_MEMORY_FILES": str(memory.get("n_files", 0)),
        "N_FEEDBACK_RULES": str(feedback_count),
        "N_PROJECT_MEMORIES": str(sum(1 for e in memory.get("entries", []) if e.get("type") == "project")),
        "N_USER_MEMORIES": str(sum(1 for e in memory.get("entries", []) if e.get("type") == "user")),
        "N_REFERENCE_MEMORIES": str(sum(1 for e in memory.get("entries", []) if e.get("type") == "reference")),
        "N_PLANS": str(plan_inv.get("n_plans", 0)),
        "N_SURGICAL": str(plan_inv.get("archetypes", {}).get("surgical", 0)),
        "N_MULTIPHASE": str(plan_inv.get("archetypes", {}).get("multi-phase", 0)),
        "N_WITH_OOS": str(plan_inv.get("has_oos_count", 0)),
        "AVG_AC_COUNT": str(plan_inv.get("avg_ac_count", 0)),
        "N_PAIRS": f"{convergence.get('n_pairs', 0):,}",
        "MEDIAN_RECOVERY": str(rec.get("median_turns", "?")),
        "P90_RECOVERY": str(rec.get("p90_turns", "?")),
        # Markdown narrative blocks
        "HEADLINE_SUMMARY": headline_md,
        "PROJECT_AREAS_NARRATIVE": project_areas_md,
        "PROJECT_GLOSSARY": project_glossary_md,
        "PROJECT_GLOSSARY_TERSE": project_glossary_md,
        "IDENTITY_SECTION": identity_section,
        "ENCODED_RULES_SECTION": encoded_rules_section,
        "ENCODED_RULES_VERBATIM": encoded_rules_section,
        "N_ENCODED_RULES": str(feedback_count),
        "TOP_ENCODED_RULES_NUMBERED_LIST": top_encoded_terse,
        "N_TOP_ENCODED_RULES": "10",
        "CANONICAL_NUMBERS": canonical,
        "WHAT_WORKS_NARRATIVE": what_works_md,
        "FRICTION_NARRATIVE": friction_md,
        "CLAUDE_MD_ADDITIONS": claude_md_md,
        "FEATURES_TO_TRY": features_md,
        "USAGE_PATTERNS_TO_KEEP": patterns_md,
        "ON_THE_HORIZON": horizon_md,
        "FUN_FINDING": fun_md,
        # HTML blocks that the template still references
        "HEADLINE_SUMMARY_HTML": md_to_html(headline_md),
        "ENCODED_RULES_CARDS_HTML": encoded_rules_cards_html,
        "CANONICAL_NUMBERS_HTML": md_to_html(canonical),
        # Structured insights-style HTML cards (PROFILE.html)
        "STATS_ROW_HTML": fmt_stats_row(stats_row_items),
        "PROJECT_AREAS_HTML": fmt_project_areas(project_area_items),
        "INTERACTION_STYLE_HTML": interaction_narrative_html,
        "KEY_PATTERN_HTML": _esc(key_pattern_text),
        "WHAT_WORKS_INTRO_HTML": _esc(big_wins_intro),
        "BIG_WINS_HTML": fmt_big_wins(big_wins_cards),
        "FRICTION_INTRO_HTML": _esc(friction_intro),
        "FRICTION_CATEGORIES_HTML": fmt_friction(friction_card_list),
        "CLAUDE_MD_ITEMS_HTML": fmt_claude_md_items(claude_md_card_items),
        "FEATURES_CARDS_HTML": fmt_features(features_card_list),
        "PATTERNS_CARDS_HTML": fmt_patterns(patterns_card_list),
        "HORIZON_INTRO_HTML": _esc(horizon_intro),
        "HORIZON_CARDS_HTML": fmt_horizon(horizon_card_list),
        "FUN_HEADLINE_HTML": _esc(fun_headline),
        "FUN_DETAIL_HTML": _esc(fun_detail),
        # Charts: ASCII for md, SVG for html
        "HOUR_HEATMAP_ASCII": hour_ascii,
        "HOUR_HEATMAP_SVG": hour_svg,
        "DAY_HISTOGRAM_ASCII": day_ascii,
        "DAY_HISTOGRAM_SVG": day_svg,
        "CONVERGENCE_BARS_ASCII": conv_ascii,
        "CONVERGENCE_DONUT_SVG": conv_svg,
        "TOP_APPROVAL_BARS_ASCII": app_bars_ascii,
        "TOP_APPROVAL_BARS_SVG": app_bars_svg,
        "TOP_PUSHBACK_BARS_ASCII": pb_bars_ascii,
        "TOP_PUSHBACK_BARS_SVG": pb_bars_svg,
        "DRIFT_CHART_ASCII": drift_ascii,
        "DRIFT_CHART_SVG": drift_svg,
        "PROMPT_LENGTH_SVG": prompt_len_svg,
        # Tables
        "TOP_FIRST_WORDS_TABLE": build_top_words_table(numbers.get("top_first_words", []), limit=30),
        "TOP_FIRST_WORDS_TABLE_HTML": build_top_words_table_html(numbers.get("top_first_words", []), limit=30),
        "TOP_APPROVAL_WORDS_TABLE": build_top_words_table(numbers.get("top_approval_words", []), limit=20),
        "TOP_PUSHBACK_WORDS_TABLE": build_top_words_table(numbers.get("top_pushback_words", []), limit=20),
        "TOP_APPROVAL_WORDS_LINE": ", ".join(
            f"`{w}`" for w, _ in (numbers.get("top_approval_words") or [])[:8]
        ) or "_no data_",
        "TOP_PUSHBACK_WORDS_LINE": ", ".join(
            f"`{w}`" for w, _ in (numbers.get("top_pushback_words") or [])[:8]
        ) or "_no data_",
        "TOP_APPROVAL_WORDS": ", ".join(
            f"`{w}`" for w, _ in (numbers.get("top_approval_words") or [])[:5]
        ) or "_no data_",
        "RISING_VOCAB": ", ".join(temporal.get("vocab_drift", {}).get("rising_in_late") or []) or "_none_",
        "FALLING_VOCAB": ", ".join(temporal.get("vocab_drift", {}).get("fell_off_in_late") or []) or "_none_",
        "NEVER_LIST": never_list,
        "NEVER_LIST_TERSE": never_list,
        "ALWAYS_LIST": always_list,
        # Legacy placeholders kept for older templates/tests; the v1 subagent
        # template is driven by render_twin_context() below.
        "OPERATING_MODEL_TERSE": render_operating_model(twin_spec),
        "DEFAULTS_SECTION": (
            "- Plan first, code second\n"
            "- Atomic commits with conventional prefix\n"
            "- Read CLAUDE.md and .decisions/ on entry\n"
            "- Terse output; no recap; no emojis"
        ),
        "CONVERGENCE_PATTERN": "concession + 2-column gap-analysis table + binary question",
        "APPROVED_TURN_TEMPLATE": (
            "1. One-sentence what-changed.\n"
            "2. 1-3 bullet evidence (file:line or quoted output).\n"
            "3. Single binary question or 'Proceed?' if no decision needed."
        ),
        "WHEN_TO_INTERVENE_SECTION": (
            "- Convention violation (back-merge as PR, renaming unused symbols, etc.)\n"
            "- Scope drift (changes outside the issue's stated AC)\n"
            "- Destructive operation without explicit prior approval\n"
            "- Output token limit risk on the current trajectory"
        ),
        "WHEN_NOT_TO_INTERVENE_SECTION": (
            "- Inside a known-good workflow (heartbeat sweep, ship-it sprint)\n"
            "- During parallel agent dispatch where each agent has self-contained brief\n"
            "- Read-only investigations (grep, glob, gh api)"
        ),
        "ESCALATION_PATHS_SECTION": (
            "1. `/codex consult` for a second opinion\n"
            "2. `AskUserQuestion` for binary decisions\n"
            "3. Stop and surface the blocker with 1-line summary + ask"
        ),
        "OUTPUT_DISCIPLINE_SECTION": (
            f"- Default reply ≤ {args.target_twin_reply_len} chars; longer only for gap analysis\n"
            f"- For long outputs, write to a file and link, do not inline\n"
            f"- No filler, no recap of what the user just said, no emojis unless asked"
        ),
        "DEFAULT_REGISTER": "terse imperative, ship-it framing",
        "TARGET_TWIN_REPLY_LEN": str(args.target_twin_reply_len),
        "MULTI_LANGUAGE_HANDLING_SECTION": (
            f"- Dominant non-English: {numbers.get('dominant_second_language') or 'none'}\n"
            f"- For product surfaces, match the project's user-facing language.\n"
            f"- For code, always English."
        ),
        "TOOLS_REACH_LIST": (
            "Bash · Read · Edit · Write · Glob · Grep · Agent · "
            "AskUserQuestion · TaskCreate · TaskList · TaskUpdate"
        ),
        "WORKFLOW_A": "Issue → Plan → Implement → Verify → PR → Merge",
        "WORKFLOW_B": "Wake payload → 6 standard checks → patch issue → close",
        "WORKFLOW_C": "PR → 4 parallel reviewers → consolidate P1/P2/P3 → fix → re-review → merge",
        "WORKFLOW_D": "Open question → 4-8 parallel research agents → synthesis pass → decision",
        "ANTI_PATTERNS_SECTION": (
            "- Over-explaining what just happened\n"
            "- Adding comments that restate code\n"
            "- Mocking dependencies in integration tests\n"
            "- Opening a PR for fast-forward back-merges\n"
            "- Asking permission for read-only inspection commands"
        ),
        "DEFAULT_PLAN_ARCHETYPE": "surgical for single-PR work, multi-phase only for >1 week scope",
        "ALWAYS_IN_PLANS": "Context, Goal, Approach, Out-of-scope, Verification",
        "VERIFICATION_GATE": "type check + tests + (UI: browser dogfood)",
        "MERGE_CONVENTION": "derive from repo conventions before acting",
        "QUALITY_BAR_TERSE": (
            "- No unhandled edge cases at PR time\n"
            "- No backfill gaps for data migrations\n"
            "- No stale references in docs"
        ),
        "CHANGED_SINCE_LAST_RUN": "(first run)",
        "TOTAL_WALL_CLOCK_MIN": "60-90",
        "RULES_MD_PATH": str(analysis / "rules.md"),
        "GENERATED_RULES_LIST": "\n".join(
            f"- `{path}`" for path in generated_rule_files.values()
        ),
    }
    ctx.update(
        render_twin_context(
            twin_spec,
            twin_spec_complete,
            args,
            compatibility_defaults=twin_spec_compat_defaults,
        )
    )

    return write_final_outputs(
        out=out,
        agents_dir=agents_dir,
        templates=templates,
        ctx=ctx,
        args=args,
        convergence=convergence,
        canonical=canonical,
        generated_rule_files=generated_rule_files,
        numbers=numbers,
        n_session_files=n_session_files,
        memory=memory,
        plan_inv=plan_inv,
        pr_stats=pr_stats,
        twin_spec_complete=twin_spec_complete,
        twin_spec_compat_defaults=twin_spec_compat_defaults,
        load_text=load_text,
        fill=fill,
        html_safe_context=html_safe_context,
        placeholder_re=PLACEHOLDER_RE,
    )


if __name__ == "__main__":
    raise SystemExit(main())
