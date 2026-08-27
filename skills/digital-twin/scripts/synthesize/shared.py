"""Shared paths, loaders, rendering, and sanitization helpers."""
from __future__ import annotations

import html
import importlib.util
import json
import re
from html.parser import HTMLParser
from pathlib import Path

# ---------------------------------------------------------------------------
# Load chart module by file path (no package machinery required)
# ---------------------------------------------------------------------------

SCRIPT_ROOT = Path(__file__).resolve().parent.parent
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


_USER_NAME_ALLOWED = re.compile(r"[^A-Za-z0-9 ._\-]")


def sanitize_user_name(value: str, max_len: int = 64) -> str:
    """Strip control chars, cap length, restrict to a safe identifier subset.

    user_name is interpolated into rendered markdown (twin agent, gotchas,
    CLAUDE patch). Newlines or markdown control sequences would inject
    content into generated files; oversize values bloat every render. Local
    env-var defaults are still trusted, but we normalize before use.
    """
    text = str(value or "").strip()
    text = _USER_NAME_ALLOWED.sub("", text)
    text = text[:max_len].strip()
    return text or "user"


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
