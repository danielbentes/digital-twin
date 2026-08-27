"""Profile formatters and legacy-profile helpers."""
from __future__ import annotations

import html
import re
from pathlib import Path

from .shared import (
    bulleted_list,
    html_table,
    load_json,
    md_table,
    md_to_html,
    md_to_html_inline as _esc,
    numbered_list,
)


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
    med = numbers.get("median_prompt_length_chars")
    if med is not None:
        parts.append(f"- Median length: {med:.0f} chars")
    p90 = numbers.get("p90_prompt_length_chars")
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
