#!/usr/bin/env python3
"""
synthesize.py — Phase 6 of the digital-twin skill.

Reads every analysis output produced by Phases 2-5 + the qualitative-agent
reports, fills the templates in references/, and writes the final artifacts to
~/.claude/digital-twin/ + ~/.claude/agents/twin.md.

Outputs (in --out directory, defaults to ~/.claude/digital-twin):
  PROFILE.md            — insights-style narrative with ASCII charts
  PROFILE.html          — same content with inline SVG charts (self-contained)
  CLAUDE-md-patch.md
  gotchas.md
  numbers.md
  _synthesis.json

Also writes ~/.claude/agents/twin.md.
"""
from __future__ import annotations

import argparse
import datetime as dt
import getpass
import html
import importlib.util
import json
import os
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

from twin_spec_validation import validate_twin_spec

# ---------------------------------------------------------------------------
# Load chart module by file path (no package machinery required)
# ---------------------------------------------------------------------------

SCRIPT_ROOT = Path(__file__).resolve().parent
PLUGIN_ROOT = SCRIPT_ROOT.parent
TWIN_SPEC_SCHEMA_PATH = PLUGIN_ROOT / "references" / "twin-spec-schema.json"
CHART_PATH = (
    PLUGIN_ROOT
    / "references" / "visualization" / "charts.py"
)
_spec = importlib.util.spec_from_file_location("charts", CHART_PATH)
if _spec is None or _spec.loader is None:
    raise RuntimeError(f"Unable to load chart module from {CHART_PATH}")
charts = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(charts)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

PLACEHOLDER_RE = re.compile(r"\{\{([A-Z_0-9]+)\}\}")
RAW_PROFILE_HTML_KEYS = {
    "BIG_WINS_HTML",
    "CANONICAL_NUMBERS_HTML",
    "CLAUDE_MD_ITEMS_HTML",
    "CONVERGENCE_DONUT_SVG",
    "DAY_HISTOGRAM_SVG",
    "DRIFT_CHART_SVG",
    "ENCODED_RULES_CARDS_HTML",
    "FEATURES_CARDS_HTML",
    "FRICTION_CATEGORIES_HTML",
    "FRICTION_INTRO_HTML",
    "FUN_DETAIL_HTML",
    "FUN_HEADLINE_HTML",
    "HEADLINE_SUMMARY_HTML",
    "HORIZON_CARDS_HTML",
    "HORIZON_INTRO_HTML",
    "HOUR_HEATMAP_SVG",
    "INTERACTION_STYLE_HTML",
    "KEY_PATTERN_HTML",
    "PATTERNS_CARDS_HTML",
    "PROJECT_AREAS_HTML",
    "PROMPT_LENGTH_SVG",
    "STATS_ROW_HTML",
    "TOP_APPROVAL_BARS_SVG",
    "TOP_PUSHBACK_BARS_SVG",
    "WHAT_WORKS_INTRO_HTML",
}


def load_json(path: Path, default=None):
    if not path.exists():
        return default
    try:
        with open(path, encoding="utf-8") as fp:
            return json.load(fp)
    except (json.JSONDecodeError, OSError):
        return default


def load_text(path: Path, default: str = "") -> str:
    if not path.exists():
        return default
    try:
        with open(path, encoding="utf-8") as fp:
            return fp.read()
    except OSError:
        return default


def fill(template: str, ctx: dict) -> str:
    def repl(match: re.Match) -> str:
        key = match.group(1)
        val = ctx.get(key)
        if val is None:
            return f"_TBD_{key}_"
        return str(val)
    return PLACEHOLDER_RE.sub(repl, template)


def html_safe_context(ctx: dict) -> dict:
    """Escape scalar placeholders before rendering the standalone HTML page."""
    safe = {}
    for key, value in ctx.items():
        value = "" if value is None else str(value)
        if key in RAW_PROFILE_HTML_KEYS:
            safe[key] = value
        else:
            safe[key] = html.escape(value, quote=True)
    return safe


def numbered_list(items: list[str]) -> str:
    return "\n".join(f"{i+1}. {x}" for i, x in enumerate(items))


def bulleted_list(items: list[str]) -> str:
    return "\n".join(f"- {x}" for x in items)


def md_table(rows: list[tuple], headers: tuple[str, ...]) -> str:
    out = ["| " + " | ".join(headers) + " |"]
    out.append("| " + " | ".join("---" for _ in headers) + " |")
    for row in rows:
        out.append("| " + " | ".join(str(c) for c in row) + " |")
    return "\n".join(out)


def html_table(rows: list[tuple], headers: tuple[str, ...]) -> str:
    out = ["<table>", "<thead><tr>"]
    for h in headers:
        out.append(f"<th>{html.escape(str(h))}</th>")
    out.append("</tr></thead><tbody>")
    for row in rows:
        out.append("<tr>")
        for c in row:
            out.append(f"<td>{md_to_html_inline(str(c))}</td>")
        out.append("</tr>")
    out.append("</tbody></table>")
    return "".join(out)


# ---------------------------------------------------------------------------
# Tiny markdown → HTML converter for the synthesized blocks.
# Handles the subset our templates produce:
#   headers (#..###), bold/italic/code, bullet/numbered lists, blockquotes,
#   GFM tables, paragraphs, blank lines.
# ---------------------------------------------------------------------------

INLINE_CODE = re.compile(r"`([^`\n]+?)`")
BOLD = re.compile(r"\*\*([^*\n]+?)\*\*")
ITALIC = re.compile(r"(?<!\*)\*([^*\n]+?)\*(?!\*)")
HEADER = re.compile(r"^(#{1,6})\s+(.*)$")
BULLET = re.compile(r"^\s*[-*]\s+(.*)$")
NUMBERED = re.compile(r"^\s*\d+\.\s+(.*)$")
BLOCKQUOTE = re.compile(r"^>\s?(.*)$")
TABLE_ROW = re.compile(r"^\s*\|(.+)\|\s*$")
TABLE_SEP = re.compile(r"^\s*\|[\s:|-]+\|\s*$")


def md_to_html_inline(text: str) -> str:
    text = html.escape(text, quote=False)
    text = INLINE_CODE.sub(r"<code>\1</code>", text)
    text = BOLD.sub(r"<strong>\1</strong>", text)
    text = ITALIC.sub(r"<em>\1</em>", text)
    return text


def md_to_html(text: str) -> str:
    """Block-level markdown → HTML."""
    if not text or not text.strip():
        return ""
    lines = text.split("\n")
    out: list[str] = []
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        # Header
        m = HEADER.match(line)
        if m:
            level = len(m.group(1)) + 2  # promote ## → h4 inside narrative
            level = min(level, 6)
            out.append(f"<h{level}>{md_to_html_inline(m.group(2))}</h{level}>")
            i += 1
            continue
        # Table
        if TABLE_ROW.match(line) and i + 1 < n and TABLE_SEP.match(lines[i + 1]):
            headers = [c.strip() for c in line.strip().strip("|").split("|")]
            i += 2
            rows: list[list[str]] = []
            while i < n and TABLE_ROW.match(lines[i]):
                cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
                rows.append(cells)
                i += 1
            out.append("<table><thead><tr>" +
                       "".join(f"<th>{md_to_html_inline(h)}</th>" for h in headers) +
                       "</tr></thead><tbody>")
            for r in rows:
                out.append("<tr>" + "".join(
                    f"<td>{md_to_html_inline(c)}</td>" for c in r
                ) + "</tr>")
            out.append("</tbody></table>")
            continue
        # Bullet list
        if BULLET.match(line):
            out.append("<ul>")
            while i < n and BULLET.match(lines[i]):
                m = BULLET.match(lines[i])
                if m is None:
                    break
                out.append(f"<li>{md_to_html_inline(m.group(1))}</li>")
                i += 1
            out.append("</ul>")
            continue
        # Numbered list
        if NUMBERED.match(line):
            out.append("<ol>")
            while i < n and NUMBERED.match(lines[i]):
                m = NUMBERED.match(lines[i])
                if m is None:
                    break
                out.append(f"<li>{md_to_html_inline(m.group(1))}</li>")
                i += 1
            out.append("</ol>")
            continue
        # Blockquote
        if BLOCKQUOTE.match(line):
            buf = []
            while i < n and BLOCKQUOTE.match(lines[i]):
                m = BLOCKQUOTE.match(lines[i])
                if m is None:
                    break
                buf.append(md_to_html_inline(m.group(1)))
                i += 1
            out.append("<blockquote>" + "<br>".join(buf) + "</blockquote>")
            continue
        # Horizontal rule
        if line.strip() in ("---", "***", "___"):
            out.append("<hr>")
            i += 1
            continue
        # Blank line → paragraph break
        if not line.strip():
            i += 1
            continue
        # Paragraph
        buf = []
        while i < n and lines[i].strip() and not (
            HEADER.match(lines[i])
            or BULLET.match(lines[i])
            or NUMBERED.match(lines[i])
            or BLOCKQUOTE.match(lines[i])
            or TABLE_ROW.match(lines[i])
        ):
            buf.append(md_to_html_inline(lines[i]))
            i += 1
        out.append("<p>" + " ".join(buf) + "</p>")
    return "\n".join(out)


_SAFE_FRAGMENT_TAGS = {"p", "strong", "em", "code", "ul", "ol", "li", "br", "blockquote"}
_DROP_FRAGMENT_TAGS = {"script", "style", "iframe", "object", "embed", "svg", "math"}


class _HTMLFragmentSanitizer(HTMLParser):
    """Strict sanitizer for LLM-produced HTML snippets."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.drop_depth = 0

    def handle_starttag(self, tag: str, attrs) -> None:  # noqa: ANN001 - HTMLParser signature
        tag = tag.lower()
        if tag in _DROP_FRAGMENT_TAGS:
            self.drop_depth += 1
            return
        if self.drop_depth or tag not in _SAFE_FRAGMENT_TAGS:
            return
        self.parts.append("<br>" if tag == "br" else f"<{tag}>")

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in _DROP_FRAGMENT_TAGS:
            if self.drop_depth:
                self.drop_depth -= 1
            return
        if self.drop_depth or tag not in _SAFE_FRAGMENT_TAGS or tag == "br":
            return
        self.parts.append(f"</{tag}>")

    def handle_data(self, data: str) -> None:
        if not self.drop_depth:
            self.parts.append(html.escape(data, quote=False))


def sanitize_html_fragment(fragment: str) -> str:
    """Return a safe HTML fragment for generated reports."""
    parser = _HTMLFragmentSanitizer()
    parser.feed(str(fragment or ""))
    parser.close()
    return "".join(parser.parts)


# ---------------------------------------------------------------------------
# Insights-style narrative builders
# ---------------------------------------------------------------------------


def build_headline_summary(numbers: dict, temporal: dict, memory: dict, convergence: dict) -> str:
    n_prompts = numbers.get("n_prompts", 0)
    n_proj = numbers.get("n_projects", 0)
    peak_h = temporal.get("peak_hour")
    peak_d = temporal.get("peak_day")
    n_pairs = convergence.get("n_pairs", 0)
    counts = convergence.get("counts", {})
    n_app = counts.get("approval", 0)
    n_pb = counts.get("explicit_pushback", 0) + counts.get("implicit_pushback", 0)
    n_rules = sum(1 for e in memory.get("entries", []) if e.get("type") == "feedback")
    approval_ratio = round(100 * n_app / max(n_pairs, 1), 1) if n_pairs else 0
    pushback_ratio = round(100 * n_pb / max(n_pairs, 1), 1) if n_pairs else 0

    lines = []
    lines.append(
        f"Across **{n_prompts:,} prompts** in **{n_proj} projects**, "
        f"the dominant pattern is concentrated work — peak activity at "
        f"**{peak_h}:00 on {peak_d}** with a clear afternoon/evening rhythm. "
        f"You ship in bursts rather than steady all-day."
    )
    lines.append("")
    lines.append(
        f"Out of **{n_pairs:,} convergence pairs** (assistant turn → user reply), "
        f"**{approval_ratio}%** are first-word approvals and **{pushback_ratio}%** are pushbacks. "
        f"You've encoded **{n_rules} feedback rules** into project memory — a high signal "
        f"that you treat corrections as durable, not one-off."
    )
    return "\n".join(lines)


def build_project_areas(numbers: dict, memory: dict, top_n: int = 5) -> str:
    project_entries = [e for e in memory.get("entries", []) if e.get("type") == "project"]
    by_proj: dict[str, list[dict]] = {}
    for e in project_entries:
        by_proj.setdefault(e["project"], []).append(e)

    top_projects = (numbers.get("per_project_top20") or [])[:top_n]
    n_total = numbers.get("n_prompts", 1) or 1

    paras = []
    for slug, count in top_projects:
        share = round(100 * count / n_total, 1)
        mems = by_proj.get(slug, [])
        descs = [
            (m.get("description") or m.get("name") or "").strip()
            for m in mems
            if (m.get("description") or m.get("name"))
        ]
        descs = [d for d in descs if d][:3]
        if descs:
            context = "; ".join(descs)
        else:
            context = "no project memory recorded — convention is unknown"
        paras.append(
            f"- **`{slug}`** ({count:,} prompts · {share}%) — {context}"
        )
    if not paras:
        return "_No per-project data available._"
    return "\n".join(paras)


def build_what_works(convergence: dict, numbers: dict, plan_inv: dict, workflow_report: str) -> str:
    counts = convergence.get("counts", {})
    n_pairs = convergence.get("n_pairs", 0) or 1
    n_app = counts.get("approval", 0)
    n_app_share = round(100 * n_app / n_pairs, 1)
    n_plans = plan_inv.get("n_plans", 0)
    n_oos = plan_inv.get("has_oos_count", 0)
    oos_pct = plan_inv.get("has_oos_pct", 0)
    top_app = (numbers.get("top_approval_words") or [])[:5]
    app_list = ", ".join(f"`{w}`" for w, _ in top_app) or "_(no data)_"

    paras = []
    paras.append(
        f"**Approval velocity.** {n_app_share}% of all convergence pairs are first-word approvals "
        f"(top steering verbs: {app_list}). Translation: when you say `go`/`ship`/`proceed`, you mean it, "
        f"and you do not ramp up to a decision over multiple turns. Match this register."
    )
    if n_plans:
        paras.append(
            f"**Out-of-scope discipline.** {n_oos} of {n_plans} plan-like documents ({oos_pct}%) "
            f"include an explicit Out-of-scope section. This is a strong signal that scope-creep "
            f"is named-and-shamed in your workflow — agents should treat OOS sections as enforceable."
        )
    drift = plan_inv.get("drift")
    if drift:
        early = drift.get("early_oos_pct", 0)
        late = drift.get("late_oos_pct", 0)
        if late > early + 5:
            paras.append(
                f"**Plan rigor is rising.** OOS adoption went from {early}% in early plans "
                f"to {late}% in recent ones — your discipline is compounding, not eroding."
            )
    # Pull a few bullet observations from the workflow report if present.
    if workflow_report:
        obs = []
        for line in workflow_report.split("\n"):
            line = line.strip()
            if line.startswith(("- ", "* ")) and (
                "parallel" in line.lower() or "ship" in line.lower()
                or "verify" in line.lower() or "merge" in line.lower()
            ):
                obs.append(line.lstrip("-* "))
        if obs[:3]:
            paras.append("**From the workflow deep-read:**")
            paras.extend(f"- {x}" for x in obs[:3])
    return "\n\n".join(paras)


def build_friction(convergence: dict, numbers: dict, temporal: dict, quality_report: str) -> str:
    counts = convergence.get("counts", {})
    n_pairs = convergence.get("n_pairs", 0) or 1
    expl_pb = counts.get("explicit_pushback", 0)
    impl_pb = counts.get("implicit_pushback", 0)
    expl_pct = round(100 * expl_pb / n_pairs, 1)
    impl_pct = round(100 * impl_pb / n_pairs, 1)
    rec = temporal.get("recovery_cycles", {})
    med_rec = rec.get("median_turns")
    p90_rec = rec.get("p90_turns")
    top_pb = (numbers.get("top_pushback_words") or [])[:5]
    pb_list = ", ".join(f"`{w}`" for w, _ in top_pb) or "_(no data)_"

    paras = []
    paras.append(
        f"**Pushback shape.** Explicit pushback fires at {expl_pct}% of pairs "
        f"(top first-words: {pb_list}). Implicit pushback — long replies with "
        f"\"but/however/actually\" markers — fires at {impl_pct}%. Together, that's "
        f"~{round(expl_pct + impl_pct, 1)}% of all turns ending in some form of correction."
    )
    if med_rec is not None:
        paras.append(
            f"**Recovery cost.** From a pushback to the next approval is a "
            f"median of {med_rec} turns (p90 {p90_rec}). Long recovery cycles correlate with "
            f"architectural rework — short ones with surface fixes."
        )
    if quality_report:
        nevers = [
            line.lstrip("-* ").strip()
            for line in quality_report.split("\n")
            if line.strip().startswith(("- NEVER ", "* NEVER ", "NEVER "))
        ][:5]
        if nevers:
            paras.append("**Encoded NEVER patterns from the quality deep-read:**")
            paras.extend(f"- {n}" for n in nevers)
    return "\n\n".join(paras)


def build_claude_md_additions(convergence: dict, numbers: dict, memory: dict) -> str:
    """Recommend additions, derived from top pushback patterns + gaps in memory."""
    additions = []
    # Existing rule descriptions for de-duplication
    existing_descs = " ".join(
        (e.get("description", "") + " " + e.get("name", "")).lower()
        for e in memory.get("entries", [])
    )
    candidates = [
        ("Output token discipline",
         "When responses risk hitting the model output limit, write to a file and link "
         "to it inline. Default reply under ~400 chars; longer only for gap analysis or final summaries.",
         ("token", "verbose", "long")),
        ("Convention check before risky actions",
         "Before opening a PR, force-pushing, or running destructive git, state the convention "
         "you're following in one sentence. If unclear, ask.",
         ("convention", "back-merge", "fast-forward")),
        ("Backfill discipline on data migrations",
         "When a schema or tagging change is shipped, enumerate which existing rows need "
         "backfill before declaring the migration complete.",
         ("backfill", "migration", "sql")),
        ("Release sync checklist",
         "On release: verify version strings, totals/counts, and stale spelled-out numbers "
         "(e.g. 'thirteen') across all docs before tagging.",
         ("release", "version", "stale")),
        ("Echo-wake recognition",
         "When an automated wake payload references work already done, recognize as echo, "
         "patch the ticket back to done, and skip the redundant cycle.",
         ("echo", "wake", "heartbeat")),
    ]
    for title, body, hints in candidates:
        if any(h in existing_descs for h in hints):
            continue
        additions.append((title, body))

    if not additions:
        return "_Your memory already covers the high-frequency friction patterns. No new additions surface from this corpus._"

    lines = []
    for title, body in additions[:5]:
        lines.append(f"**{title}**\n\n{body}\n")
    return "\n".join(lines)


def build_features_to_try(numbers: dict, plan_inv: dict, memory: dict, convergence: dict) -> str:
    feats = []
    slash_pct = numbers.get("slash_share_pct", 0) or 0
    n_pairs = convergence.get("n_pairs", 0) or 1
    impl_share = convergence.get("counts", {}).get("implicit_pushback", 0) / n_pairs
    has_mem = memory.get("n_files", 0) > 0
    n_plans = plan_inv.get("n_plans", 0)

    if slash_pct < 40:
        feats.append(
            "**Custom skills.** Reusable markdown prompts invoked with a slash command. "
            "Your slash-command share is %s%% — there's room to standardize recurring procedures "
            "(audits, releases, heartbeats) into skills."
            % round(slash_pct, 1)
        )
    feats.append(
        "**Parallel sub-agents for review/audit work.** When a task touches >2 areas "
        "(security, performance, tests, docs), dispatch a parallel agent per area and "
        "consolidate. Output bundle wins over serial deep-reads."
    )
    if impl_share > 0.1:
        feats.append(
            "**Confirm scope before review/merge.** "
            f"~{round(100*impl_share, 1)}% of replies are implicit pushback (long "
            "follow-up). Adding a one-line scope confirmation (\"reviewing branch X "
            "against convention Y\") before action would compress these cycles."
        )
    if n_plans and plan_inv.get("has_oos_pct", 0) < 60:
        feats.append(
            "**Out-of-scope sections in every plan.** Currently %s%% of your plans have one. "
            "Making it default eliminates a category of rework where Claude widens scope mid-task."
            % plan_inv.get("has_oos_pct", 0)
        )
    if has_mem:
        feats.append(
            "**`/digital-twin propose-rules` weekly.** The pushback detector queues new candidate "
            "rules between runs. Reviewing weekly turns friction into durable memory."
        )
    return "\n\n".join(feats)


def build_usage_patterns_to_keep(workflow_report: str, plan_inv: dict, convergence: dict) -> str:
    paras = []
    n_app = convergence.get("counts", {}).get("approval", 0)
    if n_app > 200:
        paras.append(
            f"**End-to-end shipping discipline.** {n_app:,} explicit approvals suggests "
            f"you regularly drive work from issue → implementation → tests → PR → merge in "
            f"a single session. Keep this — it's the highest-leverage pattern in the corpus."
        )
    if plan_inv.get("archetypes", {}).get("multi-phase", 0):
        paras.append(
            "**Phase-by-phase delivery.** Multi-phase plans (with explicit phases + AC) "
            "produce fewer rework cycles than ad-hoc surgical attempts. Keep using them for "
            "anything that touches >2 files or spans more than a day."
        )
    paras.append(
        "**Architectural pushback when conventions are violated.** Even at the cost of "
        "rework, refusing to ship convention-violating code keeps the codebase coherent. "
        "Don't soften this — agents need the friction to learn."
    )
    return "\n\n".join(paras)


def build_on_the_horizon(plan_inv: dict, convergence: dict, numbers: dict) -> str:
    paras = []
    n_multiphase = plan_inv.get("archetypes", {}).get("multi-phase", 0)
    paras.append(
        "**Self-healing automation mesh.** If you already run heartbeat tasks across repos, "
        "the next frontier is meta-agents that analyze the heartbeat history, propose "
        "threshold tuning, and emit CLAUDE.md rule patches automatically — gated on your approval."
    )
    paras.append(
        "**Multi-persona test orchestration.** For products with role-based UI (admin/user/etc), "
        "spawn one sub-agent per persona running in parallel against a shared failing-test queue "
        "until green. Compresses days of manual cross-persona QA into a single autonomous pass."
    )
    if n_multiphase >= 5:
        paras.append(
            f"**Plan archetype library.** You've written {n_multiphase} multi-phase plans. "
            "Extracting the common shape (Phase 0 setup → N implementation phases → verification "
            "→ rollback) into a `/plan-multiphase` skill would give consistent structure for free."
        )
    return "\n\n".join(paras)


def build_fun_finding(numbers: dict, temporal: dict, convergence: dict, memory: dict) -> str:
    """Surface one surprising / human observation from the data."""
    # Choose the most striking single fact.
    candidates = []
    peak_h = temporal.get("peak_hour")
    peak_count = temporal.get("peak_hour_count")
    if peak_h is not None and peak_count:
        candidates.append(
            (peak_count, f"Your single most productive hour of the day is **{peak_h}:00** "
             f"— it fires {peak_count:,} times in the corpus, well above any other hour.")
        )
    drift = (numbers.get("vocab_drift") or temporal.get("vocab_drift") or {})
    rising = drift.get("rising_in_late") or []
    falling = drift.get("fell_off_in_late") or []
    if rising and falling:
        candidates.append(
            (300, f"Your vocabulary is migrating: words rising in late corpus include "
             f"_{', '.join(rising[:3])}_, while _{', '.join(falling[:3])}_ are fading. "
             f"Your steering verbs are evolving.")
        )
    n_pb = convergence.get("counts", {}).get("explicit_pushback", 0)
    if n_pb:
        candidates.append(
            (n_pb, f"You've explicitly pushed back **{n_pb:,} times** — that's not friction, "
             "that's curation. Most of those pushbacks have a matching feedback rule in memory now.")
        )
    if not candidates:
        return "_Nothing surprising surfaced this run — try `--profile-version v0.2` after more corpus growth._"
    candidates.sort(key=lambda x: -x[0])
    return candidates[0][1]


# ---------------------------------------------------------------------------
# Insights-style structured card builders (for PROFILE.html)
#
# These mirror the /insights HTML output format: each section is a list of
# {title, description, ...} dicts that gets wrapped in the appropriate CSS
# class (.big-win, .friction-category, .feature-card, etc.).
# ---------------------------------------------------------------------------


def _esc(s: str) -> str:
    """HTML-escape, preserving common inline markdown."""
    return md_to_html_inline(s)


def _strip_md_emphasis(s: str) -> str:
    """Strip leading **bold** label that opens a narrative line."""
    s = re.sub(r"^\*\*([^*]+?)\*\*\s*", "", s.strip())
    return s.lstrip("—-. ").strip()


def _split_label_body(line: str) -> tuple[str, str]:
    """Split a `**Label.** body` line into (label, body). Returns ("", line) if no label."""
    m = re.match(r"^\s*\*\*([^*]+?)\*\*\s*\.?\s*(.*)$", line.strip())
    if m:
        return m.group(1).strip().rstrip("."), m.group(2).strip()
    return "", line.strip()


def build_what_works_cards(
    convergence: dict, numbers: dict, plan_inv: dict, workflow_report: str
) -> list[dict]:
    counts = convergence.get("counts", {})
    n_pairs = convergence.get("n_pairs", 0) or 1
    n_app = counts.get("approval", 0)
    n_app_share = round(100 * n_app / n_pairs, 1)
    n_plans = plan_inv.get("n_plans", 0)
    n_oos = plan_inv.get("has_oos_count", 0)
    oos_pct = plan_inv.get("has_oos_pct", 0)
    top_app = (numbers.get("top_approval_words") or [])[:5]
    app_list = ", ".join(f"`{w}`" for w, _ in top_app) or "(no data)"

    cards: list[dict] = []
    cards.append({
        "title": "Approval velocity",
        "description": (
            f"{n_app_share}% of all convergence pairs are first-word approvals "
            f"(top steering verbs: {app_list}). Translation: when you say `go`/`ship`/`proceed`, "
            f"you mean it — no ramp-up over multiple turns. Match this register."
        ),
    })
    if n_plans:
        cards.append({
            "title": "Out-of-scope discipline",
            "description": (
                f"{n_oos} of {n_plans} plan-like documents ({oos_pct}%) include an explicit "
                f"Out-of-scope section. Scope-creep is named-and-shamed in your workflow — "
                f"agents should treat OOS sections as enforceable."
            ),
        })
    drift = plan_inv.get("drift")
    if drift and drift.get("late_oos_pct", 0) > drift.get("early_oos_pct", 0) + 5:
        cards.append({
            "title": "Plan rigor is rising",
            "description": (
                f"OOS adoption went from {drift['early_oos_pct']}% in early plans to "
                f"{drift['late_oos_pct']}% in recent ones — your discipline is compounding, "
                f"not eroding."
            ),
        })
    if workflow_report:
        for line in workflow_report.split("\n"):
            line = line.strip()
            if line.startswith(("- ", "* ")) and any(
                kw in line.lower() for kw in ("parallel", "ship", "verify", "merge")
            ):
                clean = line.lstrip("-* ")
                label, body = _split_label_body(clean)
                if label and body:
                    cards.append({"title": label, "description": body})
                if len(cards) >= 5:
                    break
    return cards[:5]


def build_friction_cards(
    convergence: dict, numbers: dict, temporal: dict, quality_report: str
) -> list[dict]:
    counts = convergence.get("counts", {})
    n_pairs = convergence.get("n_pairs", 0) or 1
    expl = counts.get("explicit_pushback", 0)
    impl = counts.get("implicit_pushback", 0)
    expl_pct = round(100 * expl / n_pairs, 1)
    impl_pct = round(100 * impl / n_pairs, 1)
    rec = temporal.get("recovery_cycles", {})
    top_pb = (numbers.get("top_pushback_words") or [])[:5]
    pb_list = ", ".join(f"`{w}`" for w, _ in top_pb) or "(no data)"

    cards: list[dict] = []
    cards.append({
        "title": "Pushback shape",
        "description": (
            f"Explicit pushback fires at {expl_pct}% of pairs (top first-words: {pb_list}). "
            f"Implicit pushback — long replies with \"but/however/actually\" markers — fires "
            f"at {impl_pct}%. Together, ~{round(expl_pct + impl_pct, 1)}% of turns end in "
            f"some form of correction."
        ),
        "examples": [
            f"{expl} explicit pushback events",
            f"{impl} implicit (long-form, marker-laden) pushbacks",
        ],
    })
    if rec.get("median_turns") is not None:
        cards.append({
            "title": "Recovery cost",
            "description": (
                f"From a pushback to the next approval is a median of "
                f"{rec.get('median_turns')} turns (p90 {rec.get('p90_turns')}). Long recovery "
                f"cycles correlate with architectural rework; short ones with surface fixes."
            ),
            "examples": [
                f"median: {rec.get('median_turns')} turns",
                f"p90: {rec.get('p90_turns')} turns",
            ],
        })
    if quality_report:
        nevers = [
            line.lstrip("-* ").strip()
            for line in quality_report.split("\n")
            if line.strip().startswith(("- NEVER ", "* NEVER ", "NEVER "))
        ][:3]
        if nevers:
            cards.append({
                "title": "Encoded NEVER patterns",
                "description": (
                    "Patterns the quality deep-read surfaced as recurring corrections worth "
                    "encoding as durable rules."
                ),
                "examples": nevers,
            })
    return cards[:4]


def build_claude_md_items(
    convergence: dict, numbers: dict, memory: dict
) -> list[dict]:
    existing_descs = " ".join(
        (e.get("description", "") + " " + e.get("name", "")).lower()
        for e in memory.get("entries", [])
    )
    candidates = [
        ("Output token discipline",
         "## Output Token Limits\nKeep responses concise. For long outputs, write to a file "
         "and link to it inline. Default reply under ~400 chars; longer only for gap analysis.",
         "Long sessions repeatedly hit model output limits.",
         ("token", "verbose", "long")),
        ("Convention check before risky actions",
         "## Convention Confirmation\nBefore opening a PR, force-pushing, or running "
         "destructive git, state the convention you're following in one sentence. If unclear, "
         "ask.",
         "Several sessions had Claude open PRs against the wrong convention.",
         ("convention", "back-merge", "fast-forward")),
        ("Backfill discipline on data migrations",
         "## Migration Completeness\nWhen a schema or tagging change ships, enumerate which "
         "existing rows need backfill before declaring the migration complete.",
         "Recent migrations shipped without backfilling existing data.",
         ("backfill", "migration", "sql")),
        ("Release sync checklist",
         "## Release Sync\nOn release: verify version strings, totals/counts, and spelled-out "
         "numbers across all docs before tagging.",
         "Stale version references caused immediate patch releases.",
         ("release", "version", "stale")),
        ("Echo-wake recognition",
         "## Echo Wake Pattern\nWhen an automated wake payload references work already done, "
         "recognize as echo, patch the ticket back to done, and skip the redundant cycle.",
         "Automated heartbeat sessions repeatedly re-did closed work.",
         ("echo", "wake", "heartbeat")),
    ]
    out: list[dict] = []
    for title, code, why, hints in candidates:
        if any(h in existing_descs for h in hints):
            continue
        out.append({"title": title, "code": code, "why": why})
    return out[:5]


def build_features_cards(
    numbers: dict, plan_inv: dict, memory: dict, convergence: dict
) -> list[dict]:
    cards: list[dict] = []
    slash_pct = numbers.get("slash_share_pct", 0) or 0
    n_pairs = convergence.get("n_pairs", 0) or 1
    impl_share = convergence.get("counts", {}).get("implicit_pushback", 0) / n_pairs

    if slash_pct < 40:
        cards.append({
            "title": "Custom skills",
            "why": (
                f"Reusable markdown prompts invoked with a slash command. Your slash share is "
                f"{round(slash_pct, 1)}% — room to standardize recurring procedures (audits, "
                f"releases, heartbeats) as skills."
            ),
            "code": "# Create .claude/skills/audit/SKILL.md, then /audit ...",
        })
    cards.append({
        "title": "Parallel sub-agents for review/audit",
        "why": (
            "When a task spans more than two areas (security/performance/tests/docs), dispatch "
            "a parallel agent per area and consolidate. The bundle response beats serial "
            "deep-reads."
        ),
        "code": (
            "Use 4 parallel agents to review this PR: one for security, one for performance, "
            "one for tests, one for docs. Aggregate findings into P1/P2/P3 buckets."
        ),
    })
    if impl_share > 0.1:
        cards.append({
            "title": "Scope confirmation before action",
            "why": (
                f"~{round(100*impl_share, 1)}% of replies are implicit pushback (long follow-up "
                f"corrections). A one-line scope confirmation up front compresses these cycles."
            ),
            "code": (
                "Before you start: state (1) what branch/diff you'll touch, (2) what convention "
                "this repo uses, (3) any destructive ops needed. Wait for confirmation."
            ),
        })
    if plan_inv.get("n_plans", 0) and plan_inv.get("has_oos_pct", 0) < 60:
        cards.append({
            "title": "Out-of-scope sections in every plan",
            "why": (
                f"Currently {plan_inv.get('has_oos_pct', 0)}% of your plans have one. Making it "
                f"default eliminates a category of rework where Claude widens scope mid-task."
            ),
        })
    if memory.get("n_files", 0):
        cards.append({
            "title": "Weekly /digital-twin:propose-rules",
            "why": (
                "The pushback detector queues new candidate memory rules between runs. "
                "Reviewing weekly turns friction into durable rules."
            ),
        })
    return cards[:5]


def build_patterns_cards(
    workflow_report: str, plan_inv: dict, convergence: dict
) -> list[dict]:
    cards: list[dict] = []
    n_app = convergence.get("counts", {}).get("approval", 0)
    if n_app > 200:
        cards.append({
            "title": "End-to-end shipping discipline",
            "detail": (
                f"{n_app:,} explicit approvals suggests you drive work from issue → "
                f"implementation → tests → PR → merge in a single session. The highest-leverage "
                f"pattern in the corpus — keep it."
            ),
        })
    if plan_inv.get("archetypes", {}).get("multi-phase", 0):
        cards.append({
            "title": "Phase-by-phase delivery",
            "detail": (
                "Multi-phase plans (explicit phases + AC) produce fewer rework cycles than "
                "ad-hoc surgical attempts. Use them for anything touching more than two files "
                "or spanning more than a day."
            ),
        })
    cards.append({
        "title": "Architectural pushback on convention violations",
        "detail": (
            "Refusing to ship convention-violating code keeps the codebase coherent, even at "
            "the cost of rework. Don't soften this — agents need the friction signal to learn."
        ),
    })
    return cards[:4]


def build_horizon_cards(
    plan_inv: dict, convergence: dict, numbers: dict
) -> list[dict]:
    cards: list[dict] = []
    n_multiphase = plan_inv.get("archetypes", {}).get("multi-phase", 0)
    cards.append({
        "title": "Self-healing automation mesh",
        "whats_possible": (
            "If you already run heartbeat tasks across repos, the next frontier is meta-agents "
            "that analyze the heartbeat history, propose threshold tuning, and emit CLAUDE.md "
            "rule patches automatically — gated on your approval."
        ),
        "how_to_try": (
            "Combine Skills + scheduled hooks + the Agent tool to spawn meta-agents that "
            "analyze 30-day Paperclip wake history and emit policy updates."
        ),
    })
    cards.append({
        "title": "Multi-persona test orchestration",
        "whats_possible": (
            "For products with role-based UI (admin/user/etc), spawn one sub-agent per persona "
            "running in parallel against a shared failing-test queue until green. Compresses "
            "days of manual cross-persona QA into a single autonomous pass."
        ),
        "how_to_try": (
            "Use the Agent tool to launch one subagent per persona with isolated browser "
            "contexts; add a coordinator agent maintaining a shared test ledger."
        ),
    })
    if n_multiphase >= 5:
        cards.append({
            "title": "Plan archetype library",
            "whats_possible": (
                f"You've written {n_multiphase} multi-phase plans. Extracting the common shape "
                f"(Phase 0 setup → N implementation phases → verification → rollback) into a "
                f"`/plan-multiphase` skill would give consistent structure for free."
            ),
            "how_to_try": (
                "Diff your last 5 multi-phase plans and extract the shared headings into a "
                "single skill template."
            ),
        })
    return cards[:4]


def build_interaction_style(
    convergence: dict, numbers: dict, temporal: dict, memory: dict
) -> tuple[str, str]:
    """Return (narrative_html, key_pattern)."""
    counts = convergence.get("counts", {})
    n_pairs = convergence.get("n_pairs", 0) or 1
    n_app = counts.get("approval", 0)
    n_pb_total = counts.get("explicit_pushback", 0) + counts.get("implicit_pushback", 0)
    app_share = round(100 * n_app / n_pairs, 1)
    pb_share = round(100 * n_pb_total / n_pairs, 1)
    peak_h = temporal.get("peak_hour")
    peak_d = temporal.get("peak_day")
    n_rules = sum(1 for e in memory.get("entries", []) if e.get("type") == "feedback")
    n_proj = numbers.get("n_projects", 0)

    paragraphs = []
    paragraphs.append(
        f"Across {numbers.get('n_prompts', 0):,} prompts in {n_proj} projects, you "
        f"<strong>concentrate work in bursts</strong> — peak activity at {peak_h}:00 on {peak_d} "
        f"with a clear afternoon/evening rhythm rather than steady all-day output. Your average "
        f"prompt is {numbers.get('avg_prompt_length_chars', '?')} chars; you favor terse, "
        f"imperative instructions over verbose specs."
    )
    paragraphs.append(
        f"<strong>{app_share}%</strong> of your replies are first-word approvals; "
        f"<strong>{pb_share}%</strong> are pushbacks. Most of your pushback is implicit — long, "
        f"marker-laden corrections rather than blunt \"stop\". You've encoded "
        f"<strong>{n_rules} feedback rules</strong> into project memory, which tells us you "
        f"treat corrections as durable patterns worth saving, not one-off annoyances."
    )
    narrative_html = "".join(f"<p>{p}</p>" for p in paragraphs)

    if app_share > 5 and pb_share > 10:
        key = (
            "You ship in bursts with terse imperatives, but you spend long corrections on "
            "convention violations — and you encode those corrections as durable rules."
        )
    else:
        key = (
            f"Your dominant cadence is concentrated afternoon work at {peak_h}:00 on {peak_d}, "
            f"with approvals outnumbering pushbacks {app_share}% to {pb_share}%."
        )
    return narrative_html, key


def build_stats_row(numbers: dict, temporal: dict, memory: dict, convergence: dict) -> list[tuple[str, str]]:
    rec = temporal.get("recovery_cycles", {})
    n_rules = sum(1 for e in memory.get("entries", []) if e.get("type") == "feedback")
    items = [
        (f"{numbers.get('n_prompts', 0):,}", "Prompts"),
        (str(numbers.get("n_projects", 0)), "Projects"),
        (f"{temporal.get('peak_hour', '?')}:00", "Peak hour"),
        (str(temporal.get("peak_day", "?")), "Peak day"),
        (f"{numbers.get('approval_count', 0):,}", "Approvals"),
        (f"{numbers.get('pushback_count', 0):,}", "Pushbacks"),
        (str(n_rules), "Encoded rules"),
        (f"{rec.get('median_turns', '?')}", "Recovery (median)"),
    ]
    return items


def build_project_area_dicts(numbers: dict, memory: dict, top_n: int = 5) -> list[dict]:
    project_entries = [e for e in memory.get("entries", []) if e.get("type") == "project"]
    by_proj: dict[str, list[dict]] = {}
    for e in project_entries:
        by_proj.setdefault(e["project"], []).append(e)
    n_total = numbers.get("n_prompts", 1) or 1
    out = []
    for slug, count in (numbers.get("per_project_top20") or [])[:top_n]:
        share = round(100 * count / n_total, 1)
        descs = [
            (m.get("description") or m.get("name") or "").strip()
            for m in by_proj.get(slug, [])
            if (m.get("description") or m.get("name"))
        ][:2]
        desc = "; ".join(descs) if descs else (
            "No project memory recorded — convention unknown."
        )
        out.append({
            "slug": slug,
            "count": count,
            "share": share,
            "description": desc,
        })
    return out


def build_fun_parts(numbers: dict, temporal: dict, convergence: dict, memory: dict) -> tuple[str, str]:
    """Return (headline, detail)."""
    peak_h = temporal.get("peak_hour")
    peak_count = temporal.get("peak_hour_count")
    if peak_h is not None and peak_count:
        return (
            f"Your single most productive hour is {peak_h}:00",
            f"It fires {peak_count:,} times in the corpus — well above any other hour. "
            f"If you were to lose just that one hour each day, you'd lose more than {round(peak_count/24)}× "
            f"the throughput of the median hour.",
        )
    return ("Your corpus has its own shape", "Keep mining to find it.")


# ---------------------------------------------------------------------------
# HTML formatters (turn structured cards into the right CSS class wrappers)
# ---------------------------------------------------------------------------


def fmt_stats_row(items: list[tuple[str, str]]) -> str:
    return "".join(
        f'<div class="stat"><div class="stat-value">{html.escape(value)}</div>'
        f'<div class="stat-label">{html.escape(label)}</div></div>'
        for value, label in items
    )


def _src_footer(it: dict) -> str:
    """Tiny grey 'source: X' footer for cards that carry a citation."""
    src = it.get("source")
    if not src:
        return ""
    return f'<div class="card-source">source: {_esc(str(src))}</div>'


def fmt_project_areas(items: list[dict]) -> str:
    parts = []
    for it in items:
        parts.append(
            '<div class="project-area">'
            '<div class="area-header">'
            f'<div class="area-title"><code>{html.escape(it["slug"])}</code></div>'
            f'<div class="area-count">{it["count"]:,} · {it["share"]}%</div>'
            '</div>'
            f'<div class="area-description">{_esc(it["description"])}</div>'
            f'{_src_footer(it)}'
            '</div>'
        )
    return "\n".join(parts)


def fmt_big_wins(items: list[dict]) -> str:
    return "\n".join(
        f'<div class="big-win">'
        f'<div class="big-win-title">{_esc(it["title"])}</div>'
        f'<div class="big-win-description">{_esc(it["description"])}</div>'
        f'{_src_footer(it)}'
        f'</div>'
        for it in items
    )


def fmt_friction(items: list[dict]) -> str:
    parts = []
    for it in items:
        ex = ""
        if it.get("examples"):
            ex = (
                '<ul class="friction-examples">'
                + "".join(f"<li>{_esc(x)}</li>" for x in it["examples"])
                + "</ul>"
            )
        parts.append(
            f'<div class="friction-category">'
            f'<div class="friction-title">{_esc(it["title"])}</div>'
            f'<div class="friction-description">{_esc(it["description"])}</div>'
            f'{ex}'
            f'{_src_footer(it)}'
            f'</div>'
        )
    return "\n".join(parts)


def fmt_claude_md_items(items: list[dict]) -> str:
    if not items:
        return (
            '<div class="claude-md-item">'
            '<div class="cmd-why">Your memory already covers the high-frequency friction '
            'patterns from this corpus. No new additions surface.</div>'
            '</div>'
        )
    parts = []
    for it in items:
        parts.append(
            f'<div class="claude-md-item">'
            f'<code class="cmd-code">{html.escape(it["code"])}</code>'
            f'<div class="cmd-why">{_esc(it.get("why", ""))}</div>'
            f'{_src_footer(it)}'
            f'</div>'
        )
    return "\n".join(parts)


def fmt_features(items: list[dict]) -> str:
    parts = []
    for it in items:
        code = ""
        if it.get("code"):
            code = (
                f'<div class="feature-code"><code>{html.escape(it["code"])}</code></div>'
            )
        parts.append(
            f'<div class="feature-card">'
            f'<div class="feature-title">{_esc(it["title"])}</div>'
            f'<div class="feature-why">{_esc(it["why"])}</div>'
            f'{code}'
            f'{_src_footer(it)}'
            f'</div>'
        )
    return "\n".join(parts)


def fmt_patterns(items: list[dict]) -> str:
    return "\n".join(
        f'<div class="pattern-card">'
        f'<div class="pattern-title">{_esc(it["title"])}</div>'
        f'<div class="pattern-detail">{_esc(it["detail"])}</div>'
        f'{_src_footer(it)}'
        f'</div>'
        for it in items
    )


def fmt_horizon(items: list[dict]) -> str:
    return "\n".join(
        f'<div class="horizon-card">'
        f'<div class="horizon-title">{_esc(it["title"])}</div>'
        f'<div class="horizon-possible">{_esc(it["whats_possible"])}</div>'
        f'<div class="horizon-tip"><strong>How to try:</strong> {_esc(it["how_to_try"])}</div>'
        f'{_src_footer(it)}'
        f'</div>'
        for it in items
    )


# ---------------------------------------------------------------------------
# Tier 1: load extracted insights JSON (produced by extract-insights.py).
# Returns a dict keyed by section name, or None if no insights/ dir exists.
# ---------------------------------------------------------------------------

INSIGHTS_SECTIONS = (
    "project_areas",
    "interaction_style",
    "big_wins",
    "friction",
    "suggestions",
    "horizon",
    "fun_ending",
)


def load_insights(insights_dir: Path) -> dict | None:
    if not insights_dir.exists():
        return None
    out: dict = {}
    for key in INSIGHTS_SECTIONS:
        path = insights_dir / f"{key}.json"
        data = load_json(path)
        if data is None:
            continue
        out[key] = data
    # Only treat as Tier 1 if at least 4 sections loaded — otherwise the
    # extraction was incomplete and we should fall back to Tier 2.
    return out if len(out) >= 4 else None


# ---------------------------------------------------------------------------
# Markdown formatters for Tier 1 cards (so PROFILE.md mirrors PROFILE.html).
# These produce plain-text equivalents of the HTML card sections.
# ---------------------------------------------------------------------------


def _md_src(it: dict) -> str:
    src = it.get("source")
    return f"  \n_source: {src}_" if src else ""


def fmt_md_cards_titled(items: list[dict], body_key: str = "description") -> str:
    """Render cards as `### Title\n\nBody\n\n_source: X_`."""
    if not items:
        return "_no data_"
    parts = []
    for it in items:
        title = it.get("title", "")
        body = it.get(body_key, "")
        parts.append(f"### {title}\n\n{body}{_md_src(it)}")
    return "\n\n".join(parts)


def fmt_md_friction_cards(items: list[dict]) -> str:
    if not items:
        return "_no data_"
    parts = []
    for it in items:
        ex = ""
        if it.get("examples"):
            ex = "\n\nExamples:\n" + "\n".join(f"- {e}" for e in it["examples"])
        parts.append(
            f"### {it.get('title','')}\n\n{it.get('description','')}{ex}{_md_src(it)}"
        )
    return "\n\n".join(parts)


def fmt_md_claude_md_additions(items: list[dict]) -> str:
    if not items:
        return "_Your memory already covers the high-frequency friction patterns from this corpus._"
    parts = []
    for it in items:
        parts.append(
            f"### {it.get('title','')}\n\n```\n{it.get('code','')}\n```\n\n"
            f"_Why:_ {it.get('why','')}{_md_src(it)}"
        )
    return "\n\n".join(parts)


def fmt_md_features(items: list[dict]) -> str:
    if not items:
        return "_no data_"
    parts = []
    for it in items:
        code = f"\n\n```\n{it['code']}\n```" if it.get("code") else ""
        parts.append(
            f"### {it.get('title','')}\n\n{it.get('why','')}{code}{_md_src(it)}"
        )
    return "\n\n".join(parts)


def fmt_md_patterns(items: list[dict]) -> str:
    if not items:
        return "_no data_"
    return "\n\n".join(
        f"### {it.get('title','')}\n\n{it.get('detail','')}{_md_src(it)}"
        for it in items
    )


def fmt_md_horizon(items: list[dict]) -> str:
    if not items:
        return "_no data_"
    parts = []
    for it in items:
        parts.append(
            f"### {it.get('title','')}\n\n{it.get('whats_possible','')}\n\n"
            f"**How to try:** {it.get('how_to_try','')}{_md_src(it)}"
        )
    return "\n\n".join(parts)


def fmt_md_project_areas(items: list[dict]) -> str:
    if not items:
        return "_no per-project data available._"
    parts = []
    for it in items:
        slug = it.get("slug", "")
        count = it.get("count", 0)
        share = it.get("share", 0)
        desc = it.get("description", "")
        src = f" _(source: {it['source']})_" if it.get("source") else ""
        parts.append(f"- **`{slug}`** ({count:,} prompts · {share}%) — {desc}{src}")
    return "\n".join(parts)


def html_to_text(html_str: str) -> str:
    """Strip HTML tags for plaintext fallback (very lightweight)."""
    if not html_str:
        return ""
    s = re.sub(r"</p>\s*<p[^>]*>", "\n\n", html_str)
    s = re.sub(r"<[^>]+>", "", s)
    return s.strip()


# ---------------------------------------------------------------------------
# Existing section builders (kept from v0.1, modestly tightened)
# ---------------------------------------------------------------------------


def build_identity_section(memory: dict) -> str:
    user_entries = [e for e in memory.get("entries", []) if e.get("type") == "user"]
    if not user_entries:
        return "_No user-type memory files found._"
    parts = []
    for e in user_entries:
        name = e.get("name") or Path(e["path"]).stem
        desc = e.get("description") or ""
        body = e.get("body", "")
        parts.append(f"**{name}** — {desc}\n\n{body}")
    return "\n\n---\n\n".join(parts)


def build_project_glossary(memory: dict, numbers: dict) -> str:
    project_entries = [e for e in memory.get("entries", []) if e.get("type") == "project"]
    by_proj_mem: dict[str, list[dict]] = {}
    for e in project_entries:
        by_proj_mem.setdefault(e["project"], []).append(e)
    rows = []
    top_projects = numbers.get("per_project_top20") or []
    for slug, count in top_projects:
        share = round(100 * count / max(numbers.get("n_prompts", 1), 1), 1)
        mems = by_proj_mem.get(slug, [])
        if mems:
            descs = "; ".join(
                (m.get("description") or m.get("name") or "").strip()
                for m in mems if m.get("description") or m.get("name")
            )
            note = descs or "_(project memory present, no description)_"
        else:
            note = "_(no project memory; conventions unknown)_"
        rows.append((f"`{slug}`", f"{count:,}", f"{share}%", note))
    return md_table(rows, ("Project", "Prompts", "Share", "Context"))


def build_top_words_table(pairs: list[list], limit: int = 30) -> str:
    rows = [(w, f"{c:,}") for w, c in (pairs or [])[:limit]]
    return md_table(rows, ("Word", "Count")) if rows else "_no data_"


def build_top_words_table_html(pairs: list[list], limit: int = 30) -> str:
    rows = [(w, f"{c:,}") for w, c in (pairs or [])[:limit]]
    if not rows:
        return "<p><em>no data</em></p>"
    return html_table(rows, ("Word", "Count"))


def build_encoded_rules_section(memory: dict) -> str:
    feedback = [e for e in memory.get("entries", []) if e.get("type") == "feedback"]
    if not feedback:
        return "_No feedback-type memory files found._"
    parts = []
    for i, e in enumerate(feedback, 1):
        name = e.get("name") or Path(e["path"]).stem
        desc = e.get("description", "")
        body = e.get("body", "").strip()
        parts.append(f"### {i}. {name}\n\n_{desc}_\n\n{body}")
    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# Encoded-rule body parser + structured HTML renderer
# ---------------------------------------------------------------------------

RULE_MARKER_RE = re.compile(
    r"^\s*\*\*([A-Z][^*]{1,80}?):?\*\*\s*(.*)$", re.MULTILINE
)


def parse_rule_body(body: str) -> dict:
    """Split a rule body into named sections by **Label:** markers.

    Returns {"_what_": "main rule text before any marker", "<Label>": "...", ...}
    Order is preserved via insertion order (Python 3.7+ dict).
    """
    if not body:
        return {"_what_": ""}
    # Find all marker positions
    matches = list(RULE_MARKER_RE.finditer(body))
    if not matches:
        return {"_what_": body.strip()}
    sections: dict = {}
    # Pre-marker text is the "what"
    head = body[: matches[0].start()].strip()
    if head:
        sections["_what_"] = head
    for i, m in enumerate(matches):
        label = m.group(1).strip().rstrip(":").strip()
        # Everything from after this marker up to the next marker
        end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        content = body[m.end():end].strip()
        # The first inline group (m.group(2)) is content on the same line as the marker
        first_line = m.group(2).strip()
        if first_line and not content.startswith(first_line):
            content = (first_line + "\n" + content).strip()
        sections[label] = content
    return sections


def _extract_quote_from_description(desc: str) -> tuple[str, str]:
    """If the description contains a quoted user pushback, peel it out.

    Returns (cleaned_description, quote_text). quote_text is empty if no quote.
    """
    if not desc:
        return "", ""
    # Match the largest "...": substring of >= 25 chars
    m = re.search(r'"([^"]{25,400})"', desc)
    if not m:
        return desc.strip(), ""
    quote = m.group(1).strip()
    cleaned = (desc[: m.start()] + desc[m.end():]).strip(" -—,;:.").strip()
    return cleaned, quote


def _short_project(slug: str) -> str:
    """Trim a verbose project slug for display."""
    if not slug:
        return ""
    # Strip leading dash + path prefix; keep last 2-3 path components
    parts = slug.lstrip("-").split("-")
    # Heuristic: drop leading "Users-<name>-" prefix
    if len(parts) > 2 and parts[0] == "Users":
        parts = parts[2:]
    # Keep last 3 chunks at most
    if len(parts) > 4:
        parts = ["…"] + parts[-3:]
    return "/".join(parts) or slug


def fmt_encoded_rules_cards(memory: dict) -> str:
    """Render feedback rules as structured cards grouped by project.

    Each rule:
      - Header: number, name, project chip
      - Optional quoted user pushback (in amber blockquote-style)
      - Description (the YAML 'description' field, prose only)
      - Rule body parsed into sections (What / Why / How to apply / …)
    Rules within a project sit in a `<details>` block (project = summary).
    """
    feedback = [e for e in memory.get("entries", []) if e.get("type") == "feedback"]
    if not feedback:
        return '<p><em>No feedback-type memory files found.</em></p>'

    # Group by project, sort projects by rule count desc
    by_proj: dict[str, list[dict]] = {}
    for e in feedback:
        by_proj.setdefault(e.get("project", "?"), []).append(e)
    project_order = sorted(by_proj.keys(), key=lambda k: -len(by_proj[k]))

    parts = []
    counter = 0
    for proj in project_order:
        rules = by_proj[proj]
        short_proj = _short_project(proj)
        parts.append(
            f'<details class="rule-project" open>'
            f'<summary>'
            f'<span class="rule-project-name"><code>{html.escape(short_proj)}</code></span>'
            f'<span class="rule-project-count">{len(rules)} '
            f'rule{"s" if len(rules) != 1 else ""}</span>'
            f'</summary>'
            f'<div class="rule-project-body">'
        )
        for e in rules:
            counter += 1
            name = e.get("name") or Path(e["path"]).stem
            cleaned_desc, quote = _extract_quote_from_description(
                e.get("description", "")
            )
            body = e.get("body", "").strip()
            sections = parse_rule_body(body)

            parts.append('<div class="encoded-rule">')
            parts.append(
                f'<div class="encoded-rule-head">'
                f'<span class="encoded-rule-num">#{counter}</span>'
                f'<span class="encoded-rule-name">{_esc(name)}</span>'
                f'</div>'
            )
            if quote:
                parts.append(
                    f'<blockquote class="rule-quote">{_esc(quote)}</blockquote>'
                )
            if cleaned_desc:
                parts.append(
                    f'<div class="rule-desc">{_esc(cleaned_desc)}</div>'
                )
            # Render parsed sections
            what = sections.pop("_what_", "")
            if what:
                parts.append(
                    f'<div class="rule-section"><div class="rule-section-label">Rule</div>'
                    f'<div class="rule-section-body">{md_to_html(what)}</div></div>'
                )
            # Preferred order for known section labels
            preferred = ("Why", "How to apply", "How", "Do not", "Examples")
            ordered_keys = [k for k in preferred if k in sections] + [
                k for k in sections.keys() if k not in preferred
            ]
            for k in ordered_keys:
                content = sections[k]
                if not content:
                    continue
                parts.append(
                    f'<div class="rule-section">'
                    f'<div class="rule-section-label">{_esc(k)}</div>'
                    f'<div class="rule-section-body">{md_to_html(content)}</div>'
                    f'</div>'
                )
            parts.append('</div>')  # /.encoded-rule
        parts.append('</div></details>')  # /.rule-project-body /details
    return "\n".join(parts)


def build_top_encoded_rules_terse(memory: dict, top_n: int = 10) -> str:
    feedback = [e for e in memory.get("entries", []) if e.get("type") == "feedback"][:top_n]
    if not feedback:
        return "_No feedback rules yet — first run._"
    items = []
    for e in feedback:
        name = e.get("name") or Path(e["path"]).stem
        first_line = ""
        for line in e.get("body", "").split("\n"):
            line = line.strip()
            if line and not line.startswith("**") and not line.startswith("#"):
                first_line = line
                break
        items.append(f"**{name}** — {first_line}" if first_line else f"**{name}**")
    return numbered_list(items)


def build_canonical_numbers(numbers: dict, temporal: dict, plan_inv: dict) -> str:
    parts = []
    parts.append("### Prompt corpus\n")
    parts.append(f"- Total: {numbers.get('n_prompts'):,}")
    parts.append(f"- Avg length: {numbers.get('avg_prompt_length_chars')} chars")
    med = numbers.get('median_prompt_length_chars')
    if med is not None:
        parts.append(f"- Median length: {med:.0f} chars")
    p90 = numbers.get('p90_prompt_length_chars')
    if p90 is not None:
        parts.append(f"- p90 length: {p90:.0f} chars")
    total_slash = numbers.get("total_slash_invocations") or 0
    parts.append(f"- Slash invocations: {total_slash:,} ({numbers.get('slash_share_pct', 0)}%)")
    parts.append(f"- Approvals: {numbers.get('approval_count'):,}")
    parts.append(f"- Pushbacks: {numbers.get('pushback_count'):,}")
    parts.append(f"- Projects: {numbers.get('n_projects')}")
    parts.append(f"- Dominant non-English: {numbers.get('dominant_second_language') or 'none'}")
    parts.append("")
    if temporal:
        parts.append("### Temporal\n")
        rec = temporal.get("recovery_cycles", {})
        parts.append(f"- Peak hour: {temporal.get('peak_hour')}:00")
        parts.append(f"- Peak day: {temporal.get('peak_day')}")
        parts.append(f"- Recovery median turns: {rec.get('median_turns')}")
        parts.append(f"- Recovery p90 turns: {rec.get('p90_turns')}")
        parts.append("")
    if plan_inv:
        parts.append("### Plans\n")
        parts.append(f"- Total: {plan_inv.get('n_plans')}")
        parts.append(f"- Surgical: {plan_inv.get('archetypes', {}).get('surgical', 0)}")
        parts.append(f"- Multi-phase: {plan_inv.get('archetypes', {}).get('multi-phase', 0)}")
        parts.append(f"- With OOS: {plan_inv.get('has_oos_count')} ({plan_inv.get('has_oos_pct')}%)")
        parts.append(f"- Avg AC: {plan_inv.get('avg_ac_count')}")
    return "\n".join(parts)


def build_never_list(convergence: dict, encoded_rules_report: str, quality_report: str) -> str:
    items = []
    top_pb = convergence.get("first_word_top", {}).get("explicit_pushback", [])[:10]
    if top_pb:
        items.append(
            "Trigger pushback first-words: "
            + ", ".join(f"`{w}`" for w, _ in top_pb)
        )
    for report in (encoded_rules_report, quality_report):
        for line in report.split("\n"):
            line = line.strip()
            if line.startswith(("- NEVER ", "* NEVER ", "NEVER ")):
                items.append(line.lstrip("-* "))
    seen = set()
    out = []
    for it in items:
        if it not in seen:
            seen.add(it)
            out.append(it)
    return bulleted_list(out) if out else "_No explicit NEVER patterns extracted — review pushback log manually._"


def build_always_list(convergence: dict, workflow_report: str) -> str:
    items = []
    top_app = convergence.get("first_word_top", {}).get("approval", [])[:8]
    if top_app:
        items.append(
            "Earn approval first-words: "
            + ", ".join(f"`{w}`" for w, _ in top_app)
        )
    for line in workflow_report.split("\n"):
        line = line.strip()
        if line.startswith(("- ALWAYS ", "* ALWAYS ", "ALWAYS ")):
            items.append(line.lstrip("-* "))
    seen = set()
    out = []
    for it in items:
        if it not in seen:
            seen.add(it)
            out.append(it)
    return bulleted_list(out) if out else "_See workflow deep-read for ALWAYS patterns._"


# ---------------------------------------------------------------------------
# Behavioral Twin v1 rendering
# ---------------------------------------------------------------------------


def _spec_text(value, default: str = "") -> str:
    if value is None:
        return default
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


def _spec_list(values) -> list[str]:
    if not isinstance(values, list):
        return []
    out = []
    for v in values:
        if isinstance(v, str):
            s = v.strip()
        elif isinstance(v, dict):
            s = (
                v.get("rule")
                or v.get("fact")
                or v.get("title")
                or v.get("behavior")
                or ""
            ).strip()
        else:
            s = str(v).strip()
        s = re.sub(r"^\s*(?:[-*]\s+|\d+[.)]\s+)", "", s)
        if s:
            out.append(s)
    return out


def _with_evidence(text: str, evidence: str | None) -> str:
    ev = _spec_text(evidence)
    return f"{text} _(evidence: {ev})_" if ev else text


def render_identity(spec: dict) -> str:
    rows = []
    for item in spec.get("identity") or []:
        if not isinstance(item, dict):
            continue
        fact = _spec_text(item.get("fact"))
        if fact:
            rows.append(_with_evidence(fact, item.get("evidence")))
    return bulleted_list(rows) if rows else "- Behavioral spec incomplete; rerun `extract-twin-spec.py`."


def render_operating_model(spec: dict) -> str:
    op = spec.get("operating_model") or {}
    rows = []
    for label, key in (
        ("Default stance", "default_stance"),
        ("Autonomy", "autonomy_level"),
        ("Planning threshold", "planning_threshold"),
        ("Quality bar", "quality_bar"),
    ):
        val = _spec_text(op.get(key))
        if val:
            rows.append(f"**{label}:** {val}")
    ev = _spec_text(op.get("evidence"))
    if ev:
        rows.append(f"Evidence: {ev}")
    return bulleted_list(rows) if rows else "- Incomplete behavioral spec."


def render_decision_policy(spec: dict) -> str:
    pol = spec.get("decision_policy") or {}
    parts = []
    decide = _spec_list(pol.get("decide_alone"))
    esc = _spec_list(pol.get("escalate"))
    default = _spec_text(pol.get("default_assumption"))
    if decide:
        parts.append("Decide without asking:\n" + bulleted_list(decide))
    if esc:
        parts.append("Escalate:\n" + bulleted_list(esc))
    if default:
        parts.append(f"Default assumption: {default}")
    if pol.get("evidence"):
        parts.append(f"Evidence: {pol.get('evidence')}")
    return "\n\n".join(parts) if parts else "_No decision policy extracted._"


def render_delegation_policy(spec: dict) -> str:
    pol = spec.get("delegation_policy") or {}
    parts = []
    for title, key in (
        ("Use parallel agents when", "parallel_triggers"),
        ("Keep work serial when", "serial_triggers"),
        ("Use clean-context review when", "clean_context_review_triggers"),
    ):
        vals = _spec_list(pol.get(key))
        if vals:
            parts.append(f"{title}:\n" + bulleted_list(vals))
    worktree = _spec_text(pol.get("worktree_policy"))
    if worktree:
        parts.append(f"Worktree policy: {worktree}")
    if pol.get("evidence"):
        parts.append(f"Evidence: {pol.get('evidence')}")
    return "\n\n".join(parts) if parts else "_No delegation policy extracted._"


def render_workflow_policy(spec: dict) -> str:
    pol = spec.get("workflow_policy") or {}
    stages = pol.get("stages") or []
    parts = []
    for i, stage in enumerate(stages, 1):
        if not isinstance(stage, dict):
            continue
        name = _spec_text(stage.get("name"), f"Stage {i}")
        trigger = _spec_text(stage.get("trigger"))
        done = _spec_text(stage.get("done_when"))
        actions = _spec_list(stage.get("actions"))
        block = [f"{i}. **{name}**"]
        if trigger:
            block.append(f"   - Trigger: {trigger}")
        for action in actions:
            block.append(f"   - {action}")
        if done:
            block.append(f"   - Done when: {done}")
        if stage.get("evidence"):
            block.append(f"   - Evidence: {stage.get('evidence')}")
        parts.append("\n".join(block))
    if pol.get("evidence"):
        parts.append(f"Evidence: {pol.get('evidence')}")
    return "\n\n".join(parts) if parts else "_No workflow policy extracted._"


def render_verification_policy(spec: dict) -> str:
    pol = spec.get("verification_policy") or {}
    parts = []
    for title, key in (
        ("Completion claims require", "completion_claim_requires"),
        ("Fresh evidence examples", "fresh_evidence_examples"),
        ("Forbidden completion claims", "forbidden_claims"),
    ):
        vals = _spec_list(pol.get(key))
        if vals:
            parts.append(f"{title}:\n" + bulleted_list(vals))
    if pol.get("evidence"):
        parts.append(f"Evidence: {pol.get('evidence')}")
    return "\n\n".join(parts) if parts else "_No verification policy extracted._"


def render_recovery_policy(spec: dict) -> str:
    pol = spec.get("recovery_policy") or {}
    parts = []
    signals = _spec_list(pol.get("pushback_signals"))
    steps = _spec_list(pol.get("required_steps"))
    template = _spec_text(pol.get("first_response_template"))
    if signals:
        parts.append("Pushback signals:\n" + bulleted_list(signals))
    if template:
        parts.append("First response template:\n\n```markdown\n" + template + "\n```")
    if steps:
        parts.append("Required steps:\n" + numbered_list(steps))
    long_tail = _spec_text(pol.get("long_tail_escalation"))
    if long_tail:
        parts.append(f"Long-tail escalation: {long_tail}")
    if pol.get("evidence"):
        parts.append(f"Evidence: {pol.get('evidence')}")
    return "\n\n".join(parts) if parts else "_No recovery policy extracted._"


def render_voice_policy(spec: dict) -> str:
    pol = spec.get("voice_policy") or {}
    parts = []
    for label, key in (("Register", "default_register"), ("Target length", "target_length")):
        val = _spec_text(pol.get(key))
        if val:
            parts.append(f"**{label}:** {val}")
    do = _spec_list(pol.get("do"))
    avoid = _spec_list(pol.get("avoid"))
    examples = _spec_list(pol.get("examples"))
    if do:
        parts.append("Do:\n" + bulleted_list(do))
    if avoid:
        parts.append("Avoid:\n" + bulleted_list(avoid))
    if examples:
        parts.append("Examples:\n" + bulleted_list(examples))
    if pol.get("evidence"):
        parts.append(f"Evidence: {pol.get('evidence')}")
    return "\n\n".join(parts) if parts else "_No voice policy extracted._"


def render_project_routing(spec: dict) -> str:
    routing = spec.get("project_routing") or {}
    rows = []
    unknown = _spec_text(routing.get("unknown_project_behavior"))
    if unknown:
        rows.append(f"Unknown project: {unknown}")
    for proj in routing.get("projects") or []:
        if not isinstance(proj, dict):
            continue
        slug = _spec_text(proj.get("slug"))
        behavior = _spec_text(proj.get("behavior"))
        evidence = _spec_text(proj.get("evidence"))
        if slug and behavior:
            rows.append(_with_evidence(f"`{slug}`: {behavior}", evidence))
    return bulleted_list(rows) if rows else "- Unknown project: read local instructions and ask only if conventions cannot be discovered."


def render_rule_set(spec: dict, key: str, limit: int | None = None) -> str:
    rules = spec.get(key) or []
    if limit is not None:
        rules = rules[:limit]
    rows = []
    for rule in rules:
        if not isinstance(rule, dict):
            continue
        title = _spec_text(rule.get("title"))
        body = _spec_text(rule.get("rule"))
        ev = _spec_text(rule.get("evidence"))
        if not title and not body:
            continue
        line = f"**{title}** — {body}" if title and body else title or body
        rows.append(_with_evidence(line, ev))
    return numbered_list(rows) if rows else "_No rules extracted._"


def render_examples(spec: dict) -> str:
    examples = spec.get("examples") or {}
    labels = (
        ("Approved turn", "approved_turn"),
        ("Plan turn", "plan_turn"),
        ("Delegation turn", "delegation_turn"),
        ("Recovery turn", "recovery_turn"),
    )
    parts = []
    for label, key in labels:
        val = _spec_text(examples.get(key))
        if val:
            parts.append(f"### {label}\n\n```markdown\n{val}\n```")
    return "\n\n".join(parts) if parts else "_No examples extracted._"


def render_evidence_map(spec: dict, limit: int = 12) -> str:
    evidence = spec.get("evidence") or {}
    if not isinstance(evidence, dict) or not evidence:
        return "_No evidence map extracted._"
    rows = []
    for i, (key, value) in enumerate(evidence.items()):
        if i >= limit:
            break
        rows.append(f"`{key}`: {value}")
    return bulleted_list(rows)


def build_degraded_twin_spec(user_name: str, reason: str = "analysis/twin-spec.json missing") -> dict:
    return {
        "identity": [
            {
                "fact": f"{user_name}'s behavioral spec is unavailable.",
                "evidence": reason,
            },
            {
                "fact": "This agent is an incomplete fallback and should not be treated as a replacement twin.",
                "evidence": "synthesize.py degraded path",
            },
            {
                "fact": "Run extract-twin-spec.py after Phase 5.5, then rerun synthesize.py.",
                "evidence": "Behavioral Twin v1 pipeline",
            },
        ],
        "operating_model": {
            "default_stance": "Incomplete; read local instructions and avoid irreversible actions.",
            "autonomy_level": "Low until twin-spec.json exists.",
            "planning_threshold": "Plan non-trivial work before editing.",
            "quality_bar": "Do not claim completion without fresh verification evidence.",
            "evidence": "degraded fallback",
        },
        "decision_policy": {
            "decide_alone": ["Read/search files", "Summarize findings", "Run non-destructive checks"],
            "escalate": ["Destructive commands", "Merge/release/publish", "Ambiguous product decisions"],
            "default_assumption": "Prefer conservative execution until the behavioral spec is available.",
            "evidence": "degraded fallback",
        },
        "delegation_policy": {
            "parallel_triggers": ["Use only when the user explicitly asks for parallel agent work."],
            "serial_triggers": ["Recovery after pushback", "Tightly coupled implementation"],
            "worktree_policy": "Do not create worktrees unless explicitly requested.",
            "clean_context_review_triggers": ["Ask for clean review when confidence is low."],
            "evidence": "degraded fallback",
        },
        "workflow_policy": {
            "stages": [
                {"name": "Ground", "trigger": "Any non-trivial task", "actions": ["Read local instructions", "Inspect relevant files"], "done_when": "Current state is understood"},
                {"name": "Plan", "trigger": "Behavioral uncertainty", "actions": ["State assumptions", "Choose conservative path"], "done_when": "Plan is concrete"},
                {"name": "Verify", "trigger": "Before completion claim", "actions": ["Run relevant tests/checks"], "done_when": "Fresh evidence exists"},
            ],
            "evidence": "degraded fallback",
        },
        "verification_policy": {
            "completion_claim_requires": ["Fresh command output or artifact evidence"],
            "fresh_evidence_examples": ["tests", "type checks", "browser screenshots for UI"],
            "forbidden_claims": ["Do not say done based on intent or stale memory"],
            "evidence": "degraded fallback",
        },
        "recovery_policy": {
            "pushback_signals": ["wait", "stop", "no", "don't", "actually", "but"],
            "first_response_template": "Fair pushback.\n\n| What I claimed | What is actually true |\n| --- | --- |\n| ... | ... |\n\nShould I correct this path now?",
            "required_steps": ["Concede", "Name the gap", "Ask one binary question"],
            "long_tail_escalation": "After repeated mismatch, stop and ask for a concrete direction.",
            "evidence": "degraded fallback",
        },
        "voice_policy": {
            "default_register": "Concise, direct, evidence-first.",
            "target_length": "Short unless explaining a gap.",
            "do": ["Use concrete file/command evidence"],
            "avoid": ["Filler", "fake certainty", "large recaps"],
            "examples": ["Done: tests pass with fresh output."],
            "evidence": "degraded fallback",
        },
        "project_routing": {
            "unknown_project_behavior": "Read local CLAUDE.md/.decisions first; ask only if conventions remain ambiguous.",
            "projects": [],
        },
        "never_rules": [
            {"rank": 1, "title": "No fake completion", "rule": "Never claim done without fresh verification evidence.", "evidence": "degraded fallback"},
            {"rank": 2, "title": "No destructive action", "rule": "Never run destructive commands without approval.", "evidence": "degraded fallback"},
            {"rank": 3, "title": "No raw memory dump", "rule": "Do not treat profile output as an operating contract.", "evidence": "degraded fallback"},
            {"rank": 4, "title": "No scope expansion", "rule": "Do not expand beyond the active task without surfacing it.", "evidence": "degraded fallback"},
            {"rank": 5, "title": "No stale facts", "rule": "Do not rely on old session memory for branch or repo state.", "evidence": "degraded fallback"},
        ],
        "always_rules": [
            {"rank": 1, "title": "Read local context", "rule": "Read instructions and relevant files first.", "evidence": "degraded fallback"},
            {"rank": 2, "title": "Plan hard work", "rule": "Plan before non-trivial edits.", "evidence": "degraded fallback"},
            {"rank": 3, "title": "Verify", "rule": "Run relevant checks before claiming done.", "evidence": "degraded fallback"},
            {"rank": 4, "title": "Be terse", "rule": "Keep responses concise and concrete.", "evidence": "degraded fallback"},
            {"rank": 5, "title": "Escalate real ambiguity", "rule": "Ask only when facts cannot be discovered safely.", "evidence": "degraded fallback"},
        ],
        "examples": {
            "approved_turn": "Implemented and verified with fresh test output.",
            "plan_turn": "Context / Change / Verification / Out of scope.",
            "delegation_turn": "Split independent checks across agents only when requested.",
            "recovery_turn": "Fair pushback. Here is the gap and the correction path.",
        },
        "evidence": {"degraded": reason},
    }


def render_twin_context(spec: dict, complete: bool, args) -> dict:
    status = (
        "Behavioral spec complete. Use this as the operating contract."
        if complete
        else "INCOMPLETE BEHAVIORAL SPEC: this is a degraded fallback. Regenerate `analysis/twin-spec.json` before treating this as a replacement twin."
    )
    return {
        "TWIN_SPEC_STATUS": status,
        "IDENTITY_FACTS": render_identity(spec),
        "OPERATING_MODEL_SECTION": render_operating_model(spec),
        "DECISION_POLICY_SECTION": render_decision_policy(spec),
        "DELEGATION_POLICY_SECTION": render_delegation_policy(spec),
        "WORKFLOW_POLICY_SECTION": render_workflow_policy(spec),
        "VERIFICATION_POLICY_SECTION": render_verification_policy(spec),
        "RECOVERY_POLICY_SECTION": render_recovery_policy(spec),
        "VOICE_POLICY_SECTION": render_voice_policy(spec),
        "PROJECT_ROUTING_SECTION": render_project_routing(spec),
        "NEVER_RULES_TOP": render_rule_set(spec, "never_rules", limit=12),
        "ALWAYS_RULES_TOP": render_rule_set(spec, "always_rules", limit=12),
        "EXAMPLES_SECTION": render_examples(spec),
        "EVIDENCE_SECTION": render_evidence_map(spec),
        "RULES_REFERENCE_SECTION": (
            "Generated rule files live under `~/.claude/digital-twin/rules/`. "
            "Install them through `CLAUDE-md-patch.md` or symlink them into `~/.claude/rules/`."
        ),
        "DEFAULT_REGISTER": _spec_text((spec.get("voice_policy") or {}).get("default_register"), "concise, direct"),
        "TARGET_TWIN_REPLY_LEN": str(args.target_twin_reply_len),
    }


def write_rules_files(out: Path, spec: dict, generated_date: str) -> dict[str, Path]:
    rules_dir = out / "rules"
    rules_dir.mkdir(parents=True, exist_ok=True)
    files = {
        "preferences": rules_dir / "preferences.md",
        "workflows": rules_dir / "workflows.md",
        "verification": rules_dir / "verification.md",
        "recovery": rules_dir / "recovery.md",
    }
    files["preferences"].write_text(
        "\n".join([
            "# Twin Preferences",
            "",
            f"_Generated {generated_date} from behavioral twin spec._",
            "",
            "## Identity",
            render_identity(spec),
            "",
            "## Voice",
            render_voice_policy(spec),
            "",
            "## Always",
            render_rule_set(spec, "always_rules", limit=8),
            "",
            "## Never",
            render_rule_set(spec, "never_rules", limit=8),
            "",
        ]),
        encoding="utf-8",
    )
    files["workflows"].write_text(
        "\n".join([
            "# Twin Workflows",
            "",
            f"_Generated {generated_date} from behavioral twin spec._",
            "",
            "## Operating Model",
            render_operating_model(spec),
            "",
            "## Decision Policy",
            render_decision_policy(spec),
            "",
            "## Delegation Policy",
            render_delegation_policy(spec),
            "",
            "## Workflow Policy",
            render_workflow_policy(spec),
            "",
            "## Project Routing",
            render_project_routing(spec),
            "",
        ]),
        encoding="utf-8",
    )
    files["verification"].write_text(
        "\n".join([
            "# Twin Verification",
            "",
            f"_Generated {generated_date} from behavioral twin spec._",
            "",
            render_verification_policy(spec),
            "",
        ]),
        encoding="utf-8",
    )
    files["recovery"].write_text(
        "\n".join([
            "# Twin Recovery",
            "",
            f"_Generated {generated_date} from behavioral twin spec._",
            "",
            render_recovery_policy(spec),
            "",
        ]),
        encoding="utf-8",
    )
    return files


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


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
    ap.add_argument("--templates", default=str(Path(__file__).resolve().parent.parent / "references"))
    ap.add_argument("--user-name", default=os.environ.get("DIGITAL_TWIN_USER_NAME", getpass.getuser()))
    ap.add_argument("--profile-version", default="v0.1")
    ap.add_argument("--target-twin-reply-len", type=int, default=600)
    args = ap.parse_args()

    analysis = Path(args.analysis).expanduser()
    reports = Path(args.reports).expanduser()
    out = Path(args.out).expanduser()
    agents_dir = Path(args.agents_dir).expanduser()
    templates = Path(args.templates).expanduser()

    out.mkdir(parents=True, exist_ok=True)
    agents_dir.mkdir(parents=True, exist_ok=True)

    numbers = load_json(analysis / "numbers.json", default={}) or {}
    temporal = load_json(analysis / "temporal.json", default={}) or {}
    memory = load_json(analysis / "memory-inventory.json", default={}) or {}
    plan_inv = load_json(analysis / "plan-inventory.json", default={}) or {}
    convergence = load_json(analysis / "convergence-pairs.json", default={}) or {}
    pr_stats = load_json(analysis / "pr-comments.json", default={}) or {}
    twin_spec_path = analysis / "twin-spec.json"
    twin_spec = load_json(twin_spec_path, default=None)
    twin_spec_complete = isinstance(twin_spec, dict) and bool(twin_spec)
    if twin_spec_complete:
        twin_spec_errors = validate_twin_spec(twin_spec, TWIN_SPEC_SCHEMA_PATH)
        if twin_spec_errors:
            twin_spec_complete = False
            reason = (
                f"{twin_spec_path} failed schema validation: "
                + "; ".join(twin_spec_errors[:5])
            )
            print(f"WARN: {reason}", file=sys.stderr)
            twin_spec = build_degraded_twin_spec(args.user_name, reason=reason)
    else:
        reason = f"{twin_spec_path} missing"
        print(
            "WARN: analysis/twin-spec.json missing; writing degraded twin agent",
            file=sys.stderr,
        )
        twin_spec = build_degraded_twin_spec(args.user_name, reason=reason)

    orchestration_report = load_text(reports / "orchestration.md")
    workflow_report = load_text(reports / "workflow.md")
    quality_report = load_text(reports / "quality.md")
    encoded_rules_report = load_text(reports / "encoded-rules.md")

    n_session_files = numbers.get("n_session_files") or "?"
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
        "MERGE_CONVENTION": "_TBD_ (review your repo conventions)",
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
    ctx.update(render_twin_context(twin_spec, twin_spec_complete, args))

    # --- Profile (markdown) ---
    profile_template = load_text(templates / "profile-template.md")
    profile_md = fill(profile_template, ctx)
    profile_out = out / "PROFILE.md"
    profile_out.write_text(profile_md, encoding="utf-8")

    # --- Profile (HTML) ---
    profile_html_template = load_text(templates / "profile-template.html")
    profile_html = fill(profile_html_template, html_safe_context(ctx))
    profile_html_out = out / "PROFILE.html"
    profile_html_out.write_text(profile_html, encoding="utf-8")

    # --- Twin agent ---
    twin_template = load_text(templates / "subagent-template.md")
    twin_md = fill(twin_template, ctx)
    twin_out = agents_dir / "twin.md"
    twin_out.write_text(twin_md, encoding="utf-8")

    # --- CLAUDE.md patch ---
    patch_template = load_text(templates / "claude-patch-template.md")
    patch_md = fill(patch_template, ctx)
    patch_out = out / "CLAUDE-md-patch.md"
    patch_out.write_text(patch_md, encoding="utf-8")

    # --- gotchas.md ---
    gotchas_md = (
        f"# Gotchas — {args.user_name}'s digital twin\n\n"
        f"_Generated {dt.date.today().isoformat()} · seed list from pushback analysis._\n\n"
        f"## Pushback first-words (top 10)\n\n"
    )
    pb = convergence.get("first_word_top", {}).get("explicit_pushback", [])[:10]
    for i, (w, c) in enumerate(pb, 1):
        gotchas_md += f"{i}. `{w}` ({c} occurrences)\n"
    gotchas_md += "\n## Implicit-pushback first-words (top 10)\n\n"
    for i, (w, c) in enumerate(
        convergence.get("first_word_top", {}).get("implicit_pushback", [])[:10], 1
    ):
        gotchas_md += f"{i}. `{w}` ({c} occurrences)\n"
    gotchas_md += (
        "\n## Next steps\n\n"
        "Edit this file to add named gotchas as you encounter them. "
        "When you tell Claude Code to 'avoid X', add X here so the twin "
        "remembers between sessions.\n"
    )
    (out / "gotchas.md").write_text(gotchas_md, encoding="utf-8")

    # --- canonical numbers ---
    canonical_md = (
        f"# Canonical numbers — source of truth\n\n"
        f"_Generated {dt.date.today().isoformat()}_\n\n"
        f"{canonical}\n\n"
        "_Every figure in PROFILE.md, twin.md, and CLAUDE-md-patch.md is derived "
        "from these values. If they disagree, this file wins; regenerate the others._\n"
    )
    (out / "numbers.md").write_text(canonical_md, encoding="utf-8")

    # --- run metadata ---
    meta = {
        "generated_at": dt.datetime.now().isoformat(),
        "user_name": args.user_name,
        "profile_version": args.profile_version,
        "prompt_count": numbers.get("n_prompts"),
        "n_session_files": numbers.get("n_session_files"),
        "n_projects": numbers.get("n_projects"),
        "n_memory_files": memory.get("n_files"),
        "n_plans": plan_inv.get("n_plans"),
        "n_convergence_pairs": convergence.get("n_pairs"),
        "had_pr_mining": bool(pr_stats and not pr_stats.get("skipped")),
        "had_twin_spec": twin_spec_complete,
        "outputs": {
            "profile_md": str(profile_out),
            "profile_html": str(profile_html_out),
            "twin": str(twin_out),
            "claude_md_patch": str(patch_out),
            "gotchas": str(out / "gotchas.md"),
            "numbers": str(out / "numbers.md"),
            "rules": {name: str(path) for name, path in generated_rule_files.items()},
        },
    }
    (out / "_synthesis.json").write_text(
        json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    print(f"Wrote: {profile_out}")
    print(f"Wrote: {profile_html_out}")
    print(f"Wrote: {twin_out}")
    print(f"Wrote: {patch_out}")
    print(f"Wrote: {out / 'gotchas.md'}")
    print(f"Wrote: {out / 'numbers.md'}")
    print(f"Wrote: {out / '_synthesis.json'}")

    unfilled = set(PLACEHOLDER_RE.findall(profile_md + twin_md + patch_md + profile_html))
    if unfilled:
        print(f"\nNote: {len(unfilled)} placeholders still need values:")
        for k in sorted(unfilled):
            print(f"  - {{{{ {k} }}}}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
