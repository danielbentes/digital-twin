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
from pathlib import Path

# ---------------------------------------------------------------------------
# Load chart module by file path (no package machinery required)
# ---------------------------------------------------------------------------

CHART_PATH = (
    Path(__file__).resolve().parent.parent
    / "references" / "visualization" / "charts.py"
)
_spec = importlib.util.spec_from_file_location("charts", CHART_PATH)
charts = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(charts)  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

PLACEHOLDER_RE = re.compile(r"\{\{([A-Z_0-9]+)\}\}")


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
                out.append(f"<li>{md_to_html_inline(m.group(1))}</li>")
                i += 1
            out.append("</ul>")
            continue
        # Numbered list
        if NUMBERED.match(line):
            out.append("<ol>")
            while i < n and NUMBERED.match(lines[i]):
                m = NUMBERED.match(lines[i])
                out.append(f"<li>{md_to_html_inline(m.group(1))}</li>")
                i += 1
            out.append("</ol>")
            continue
        # Blockquote
        if BLOCKQUOTE.match(line):
            buf = []
            while i < n and BLOCKQUOTE.match(lines[i]):
                m = BLOCKQUOTE.match(lines[i])
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
        f"**Self-healing automation mesh.** If you already run heartbeat tasks across repos, "
        f"the next frontier is meta-agents that analyze the heartbeat history, propose "
        f"threshold tuning, and emit CLAUDE.md rule patches automatically — gated on your approval."
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
        f'<div class="stat"><div class="stat-value">{html.escape(v)}</div>'
        f'<div class="stat-label">{html.escape(l)}</div></div>'
        for v, l in items
    )


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
            '</div>'
        )
    return "\n".join(parts)


def fmt_big_wins(items: list[dict]) -> str:
    return "\n".join(
        f'<div class="big-win">'
        f'<div class="big-win-title">{_esc(it["title"])}</div>'
        f'<div class="big-win-description">{_esc(it["description"])}</div>'
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
            f'</div>'
        )
    return "\n".join(parts)


def fmt_patterns(items: list[dict]) -> str:
    return "\n".join(
        f'<div class="pattern-card">'
        f'<div class="pattern-title">{_esc(it["title"])}</div>'
        f'<div class="pattern-detail">{_esc(it["detail"])}</div>'
        f'</div>'
        for it in items
    )


def fmt_horizon(items: list[dict]) -> str:
    return "\n".join(
        f'<div class="horizon-card">'
        f'<div class="horizon-title">{_esc(it["title"])}</div>'
        f'<div class="horizon-possible">{_esc(it["whats_possible"])}</div>'
        f'<div class="horizon-tip"><strong>How to try:</strong> {_esc(it["how_to_try"])}</div>'
        f'</div>'
        for it in items
    )


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


def build_project_glossary_html(memory: dict, numbers: dict) -> str:
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
            note = descs or "<em>project memory present, no description</em>"
        else:
            note = "<em>no project memory; conventions unknown</em>"
        rows.append((f"<code>{html.escape(slug)}</code>",
                     f"{count:,}",
                     f"{share}%",
                     md_to_html_inline(note)))
    out = ["<table><thead><tr>"]
    out.extend(f"<th>{h}</th>" for h in ("Project", "Prompts", "Share", "Context"))
    out.append("</tr></thead><tbody>")
    for r in rows:
        out.append("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>")
    out.append("</tbody></table>")
    return "".join(out)


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
    parts.append(f"- Slash invocations: {numbers.get('total_slash_invocations'):,} ({numbers.get('slash_share_pct')}%)")
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

    orchestration_report = load_text(reports / "orchestration.md")
    workflow_report = load_text(reports / "workflow.md")
    quality_report = load_text(reports / "quality.md")
    encoded_rules_report = load_text(reports / "encoded-rules.md")
    planning_report = load_text(reports / "planning-style.md")
    recovery_report = load_text(reports / "failure-recovery.md")

    n_session_files = numbers.get("n_session_files") or "?"
    date_range = "?"
    if temporal.get("date_range"):
        d = temporal["date_range"]
        date_range = f"{d['start'][:10]} → {d['end'][:10]}"

    # Sections
    project_glossary_md = build_project_glossary(memory, numbers)
    project_glossary_html = build_project_glossary_html(memory, numbers)
    identity_section = build_identity_section(memory)
    encoded_rules_section = build_encoded_rules_section(memory)
    top_encoded_terse = build_top_encoded_rules_terse(memory, top_n=10)
    canonical = build_canonical_numbers(numbers, temporal, plan_inv)
    never_list = build_never_list(convergence, encoded_rules_report, quality_report)
    always_list = build_always_list(convergence, workflow_report)

    headline = build_headline_summary(numbers, temporal, memory, convergence)
    project_areas = build_project_areas(numbers, memory, top_n=5)
    what_works = build_what_works(convergence, numbers, plan_inv, workflow_report)
    friction = build_friction(convergence, numbers, temporal, quality_report)
    claude_md_adds = build_claude_md_additions(convergence, numbers, memory)
    features_try = build_features_to_try(numbers, plan_inv, memory, convergence)
    usage_keep = build_usage_patterns_to_keep(workflow_report, plan_inv, convergence)
    horizon = build_on_the_horizon(plan_inv, convergence, numbers)
    fun = build_fun_finding(numbers, temporal, convergence, memory)

    # Structured cards for the /insights-style HTML output
    big_wins_cards = build_what_works_cards(convergence, numbers, plan_inv, workflow_report)
    friction_card_list = build_friction_cards(convergence, numbers, temporal, quality_report)
    claude_md_card_items = build_claude_md_items(convergence, numbers, memory)
    features_card_list = build_features_cards(numbers, plan_inv, memory, convergence)
    patterns_card_list = build_patterns_cards(workflow_report, plan_inv, convergence)
    horizon_card_list = build_horizon_cards(plan_inv, convergence, numbers)
    interaction_narrative_html, key_pattern_text = build_interaction_style(
        convergence, numbers, temporal, memory
    )
    stats_row_items = build_stats_row(numbers, temporal, memory, convergence)
    project_area_items = build_project_area_dicts(numbers, memory, top_n=5)
    fun_headline, fun_detail = build_fun_parts(numbers, temporal, convergence, memory)

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

    # Stat cards (HTML only)
    rec = temporal.get("recovery_cycles", {})
    feedback_count = sum(1 for e in memory.get("entries", []) if e.get("type") == "feedback")
    stat_cards = charts.stat_cards_svg([
        ("Prompts", f"{numbers.get('n_prompts', 0):,}"),
        ("Projects", str(numbers.get("n_projects", 0))),
        ("Peak hour", f"{temporal.get('peak_hour', '?')}:00"),
        ("Peak day", str(temporal.get("peak_day", "?"))),
        ("Approvals", f"{numbers.get('approval_count', 0):,}"),
        ("Pushbacks", f"{numbers.get('pushback_count', 0):,}"),
        ("Encoded rules", str(feedback_count)),
        ("Recovery median", f"{rec.get('median_turns', '?')} turns"),
    ])

    ctx = {
        "USER_NAME": args.user_name,
        "GENERATED_DATE": dt.date.today().isoformat(),
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
        "DRIFT_SUMMARY": str(plan_inv.get("drift") or "_insufficient plans for drift_"),
        "N_PAIRS": f"{convergence.get('n_pairs', 0):,}",
        "MEDIAN_RECOVERY": str(rec.get("median_turns", "?")),
        "P90_RECOVERY": str(rec.get("p90_turns", "?")),
        # Markdown narrative blocks
        "HEADLINE_SUMMARY": headline,
        "PROJECT_AREAS_NARRATIVE": project_areas,
        "PROJECT_GLOSSARY": project_glossary_md,
        "PROJECT_GLOSSARY_TERSE": project_glossary_md,
        "IDENTITY_SECTION": identity_section,
        "ORCHESTRATION_SECTION": orchestration_report or "_pending — run Phase 4 agent_",
        "ORCHESTRATION_REPORT_PATH": str(reports / "orchestration.md"),
        "WORKFLOW_SECTION": workflow_report or "_pending_",
        "WORKFLOW_REPORT_PATH": str(reports / "workflow.md"),
        "QUALITY_SECTION": quality_report or "_pending_",
        "QUALITY_REPORT_PATH": str(reports / "quality.md"),
        "PLANNING_SECTION": planning_report or "_pending_",
        "RECOVERY_SECTION": recovery_report or "_pending_",
        "ENCODED_RULES_SECTION": encoded_rules_section,
        "ENCODED_RULES_VERBATIM": encoded_rules_section,
        "N_ENCODED_RULES": str(feedback_count),
        "TOP_ENCODED_RULES_NUMBERED_LIST": top_encoded_terse,
        "N_TOP_ENCODED_RULES": "10",
        "CANONICAL_NUMBERS": canonical,
        "WHAT_WORKS_NARRATIVE": what_works,
        "FRICTION_NARRATIVE": friction,
        "CLAUDE_MD_ADDITIONS": claude_md_adds,
        "FEATURES_TO_TRY": features_try,
        "USAGE_PATTERNS_TO_KEEP": usage_keep,
        "ON_THE_HORIZON": horizon,
        "FUN_FINDING": fun,
        # HTML narrative blocks
        "HEADLINE_SUMMARY_HTML": md_to_html(headline),
        "PROJECT_AREAS_NARRATIVE_HTML": md_to_html(project_areas),
        "PROJECT_GLOSSARY_HTML": project_glossary_html,
        "IDENTITY_SECTION_HTML": md_to_html(identity_section),
        "ORCHESTRATION_SECTION_HTML": md_to_html(orchestration_report or "_pending_"),
        "WORKFLOW_SECTION_HTML": md_to_html(workflow_report or "_pending_"),
        "QUALITY_SECTION_HTML": md_to_html(quality_report or "_pending_"),
        "PLANNING_SECTION_HTML": md_to_html(planning_report or "_pending_"),
        "RECOVERY_SECTION_HTML": md_to_html(recovery_report or "_pending_"),
        "ENCODED_RULES_SECTION_HTML": md_to_html(encoded_rules_section),
        "CANONICAL_NUMBERS_HTML": md_to_html(canonical),
        "WHAT_WORKS_NARRATIVE_HTML": md_to_html(what_works),
        "FRICTION_NARRATIVE_HTML": md_to_html(friction),
        "CLAUDE_MD_ADDITIONS_HTML": md_to_html(claude_md_adds),
        "FEATURES_TO_TRY_HTML": md_to_html(features_try),
        "USAGE_PATTERNS_TO_KEEP_HTML": md_to_html(usage_keep),
        "ON_THE_HORIZON_HTML": md_to_html(horizon),
        "FUN_FINDING_HTML": md_to_html(fun),
        # Structured insights-style HTML cards (PROFILE.html)
        "STATS_ROW_HTML": fmt_stats_row(stats_row_items),
        "PROJECT_AREAS_HTML": fmt_project_areas(project_area_items),
        "INTERACTION_STYLE_HTML": interaction_narrative_html,
        "KEY_PATTERN_HTML": _esc(key_pattern_text),
        "WHAT_WORKS_INTRO_HTML": _esc(
            f"Patterns that compound across {numbers.get('n_prompts', 0):,} prompts — "
            f"keep them; they're load-bearing."
        ),
        "BIG_WINS_HTML": fmt_big_wins(big_wins_cards),
        "FRICTION_INTRO_HTML": _esc(
            "Where friction shows up most often. Each pattern is a candidate for an "
            "encoded memory rule."
        ),
        "FRICTION_CATEGORIES_HTML": fmt_friction(friction_card_list),
        "CLAUDE_MD_ITEMS_HTML": fmt_claude_md_items(claude_md_card_items),
        "FEATURES_CARDS_HTML": fmt_features(features_card_list),
        "PATTERNS_CARDS_HTML": fmt_patterns(patterns_card_list),
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
        "STAT_CARDS_SVG": stat_cards,
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
        # Twin agent context (unchanged from v0.1)
        "OPERATING_MODEL_SECTION": "_See PROFILE.md Part 3 for orchestration deep read._",
        "OPERATING_MODEL_TERSE": (
            "- Default delegation: parallel agents when work spans >2 areas\n"
            "- Approval gates at: plan, post-impl, pre-merge\n"
            "- Verification before 'ship': type check + tests + (UI cases: browser)"
        ),
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
            "AskUserQuestion · TaskCreate · TaskList · TaskUpdate · WebFetch"
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
    }

    # --- Profile (markdown) ---
    profile_template = load_text(templates / "profile-template.md")
    profile_md = fill(profile_template, ctx)
    profile_out = out / "PROFILE.md"
    profile_out.write_text(profile_md, encoding="utf-8")

    # --- Profile (HTML) ---
    profile_html_template = load_text(templates / "profile-template.html")
    profile_html = fill(profile_html_template, ctx)
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
        "outputs": {
            "profile_md": str(profile_out),
            "profile_html": str(profile_html_out),
            "twin": str(twin_out),
            "claude_md_patch": str(patch_out),
            "gotchas": str(out / "gotchas.md"),
            "numbers": str(out / "numbers.md"),
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
