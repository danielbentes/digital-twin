"""
Tests for the Phase 4.5 insights extraction + three-tier synthesize fallback.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = PLUGIN_ROOT / "skills" / "digital-twin" / "scripts"
REFERENCES = PLUGIN_ROOT / "skills" / "digital-twin" / "references"
EXTRACT = SCRIPTS / "extract-insights.py"
SYNTH = SCRIPTS / "synthesize.py"

# Make the scripts importable so we can test fmt_* directly.
sys.path.insert(0, str(SCRIPTS))


def _golden_insights() -> dict:
    """A complete fixture covering all 7 sections."""
    return {
        "project_areas": [
            {"slug": "-proj-alpha", "count": 1200, "share": 30.0,
             "description": "Main product backend",
             "source": "workflow.md §1"},
            {"slug": "-proj-beta", "count": 800, "share": 20.0,
             "description": "ML training harness",
             "source": "workflow.md §2"},
        ],
        "interaction_style": {
            "narrative_html": "<p>You favor terse, imperative prompts.</p><p>You push back with markers like <strong>actually</strong>.</p>",
            "key_pattern": "Terse imperatives plus marker-laden corrections.",
            "source": "quality.md"
        },
        "big_wins": {
            "intro": "Patterns that compound.",
            "cards": [
                {"title": "End-to-end shipping",
                 "description": "You drive from issue to merge in a single session.",
                 "source": "workflow.md §3"},
                {"title": "Parallel agent dispatch",
                 "description": "You use parallel review agents for big PRs.",
                 "source": "orchestration.md §2"},
            ]
        },
        "friction": {
            "intro": "Where corrections cluster.",
            "cards": [
                {"title": "Output token overruns",
                 "description": "Long verbose responses hit limits.",
                 "examples": ["session XYZ truncated at 500 tokens",
                              "request to write to file instead"],
                 "source": "failure-recovery.md §1"},
                {"title": "Convention drift",
                 "description": "Agents miss project-specific conventions.",
                 "source": "quality.md §4"},
            ]
        },
        "suggestions": {
            "claude_md_additions": [
                {"title": "Output token discipline",
                 "code": "## Output Token Limits\nKeep responses under 400 chars.",
                 "why": "Multiple sessions hit the 500-token wall.",
                 "source": "friction.md"},
            ],
            "features_to_try": [
                {"title": "Custom skills",
                 "why": "You repeat workflows across projects.",
                 "code": "mkdir -p .claude/skills/audit",
                 "source": "patterns.md"},
            ],
            "patterns_to_keep": [
                {"title": "Architectural pushback",
                 "detail": "Refusing convention-violating code keeps the codebase coherent.",
                 "source": "quality.md"},
            ],
        },
        "horizon": {
            "intro": "Forward-looking moves.",
            "cards": [
                {"title": "Self-healing automation mesh",
                 "whats_possible": "Meta-agents propose threshold tuning.",
                 "how_to_try": "Run a weekly diff over heartbeat sessions.",
                 "source": "orchestration.md"},
                {"title": "Plan archetype library",
                 "whats_possible": "Extract shared multi-phase plan shape.",
                 "how_to_try": "Diff last 5 plans.",
                 "source": "planning-style.md"},
            ]
        },
        "fun_ending": {
            "headline": "Your most productive hour is 16:00",
            "detail": "It fires more than any other hour by a wide margin.",
            "source": "temporal.json"
        },
    }


def _write_insights(insights_dir: Path, data: dict) -> None:
    insights_dir.mkdir(parents=True, exist_ok=True)
    for key, value in data.items():
        (insights_dir / f"{key}.json").write_text(
            json.dumps(value, indent=2), encoding="utf-8"
        )


def _write_minimal_analysis(analysis: Path, insights: dict | None = None) -> None:
    analysis.mkdir(parents=True, exist_ok=True)
    (analysis / "numbers.json").write_text(json.dumps({
        "n_prompts": 100,
        "n_projects": 2,
        "approval_count": 50,
        "pushback_count": 5,
        "slash_share_pct": 10,
        "n_session_files": 5,
        "total_slash_invocations": 10,
        "avg_prompt_length_chars": 100,
        "median_prompt_length_chars": 80,
        "p90_prompt_length_chars": 200,
        "dominant_second_language": None,
        "top_approval_words": [],
        "top_pushback_words": [],
        "top_first_words": [],
        "per_project_top20": [],
    }))
    (analysis / "temporal.json").write_text(json.dumps({
        "hour_histogram": {str(h): 0 for h in range(24)},
        "dow_histogram": {"Mon": 0},
        "peak_hour": 16,
        "peak_day": "Wed",
        "recovery_cycles": {"median_turns": 5, "p90_turns": 20},
        "vocab_drift": {},
    }))
    (analysis / "memory-inventory.json").write_text(json.dumps({
        "n_files": 0,
        "by_type": {},
        "entries": [],
    }))
    (analysis / "plan-inventory.json").write_text(json.dumps({
        "n_plans": 0,
        "archetypes": {},
        "has_oos_count": 0,
        "has_oos_pct": 0,
    }))
    (analysis / "convergence-pairs.json").write_text(json.dumps({
        "n_pairs": 100,
        "counts": {
            "approval": 50,
            "explicit_pushback": 5,
            "implicit_pushback": 10,
            "neutral": 35,
        },
        "first_word_top": {},
    }))
    if insights is not None:
        _write_insights(analysis / "insights", insights)


def _run_synthesize(tmp_path: Path, analysis: Path, user_name: str = "TestUser"):
    out = tmp_path / "out"
    out.mkdir()
    agents = tmp_path / "agents"
    agents.mkdir()
    empty_reports = tmp_path / "no-reports"
    empty_reports.mkdir()
    return subprocess.run(
        [sys.executable, str(SYNTH),
         "--analysis", str(analysis),
         "--reports", str(empty_reports),
         "--out", str(out),
         "--agents-dir", str(agents),
         "--user-name", user_name],
        capture_output=True,
        text=True,
    ), out


# ---------------------------------------------------------------------------
# Test 1 — schema round-trip
# ---------------------------------------------------------------------------


def test_schema_round_trip():
    """Golden insights data validates against the schema's required fields."""
    data = _golden_insights()
    # The synthesize.py validate_section logic is the source of truth.
    sys.path.insert(0, str(SCRIPTS))
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "extract_insights",
        str(EXTRACT),
    )
    ext = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ext)
    errs = ext.validate_all(data)
    assert not errs, f"validation errors: {errs}"


# ---------------------------------------------------------------------------
# Test 2 — renderers consume JSON
# ---------------------------------------------------------------------------


def test_renderer_consumes_json():
    import importlib.util
    spec = importlib.util.spec_from_file_location("synthesize", str(SYNTH))
    syn = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(syn)

    data = _golden_insights()
    big = syn.fmt_big_wins(data["big_wins"]["cards"])
    assert 'class="big-win"' in big
    assert "End-to-end shipping" in big
    assert "source: workflow.md §3" in big

    friction = syn.fmt_friction(data["friction"]["cards"])
    assert 'class="friction-category"' in friction
    assert "session XYZ truncated" in friction

    features = syn.fmt_features(data["suggestions"]["features_to_try"])
    assert 'class="feature-card"' in features
    assert "Custom skills" in features

    horizon = syn.fmt_horizon(data["horizon"]["cards"])
    assert 'class="horizon-card"' in horizon
    assert "Self-healing automation mesh" in horizon

    cmd = syn.fmt_claude_md_items(data["suggestions"]["claude_md_additions"])
    assert 'class="claude-md-item"' in cmd
    assert "## Output Token Limits" in cmd


def test_profile_html_hardening_helpers_escape_untrusted_fragments():
    import importlib.util
    spec = importlib.util.spec_from_file_location("synthesize", str(SYNTH))
    syn = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(syn)

    dirty = (
        '<p onclick="steal()">Safe <strong>bold</strong>'
        '<img src="x" onerror="steal()">'
        '<script>alert(1)</script>'
        '<a href="javascript:steal()">link</a></p>'
    )
    clean = syn.sanitize_html_fragment(dirty)
    assert "<strong>bold</strong>" in clean
    assert "<script" not in clean
    assert "alert(1)" not in clean
    assert "<img" not in clean
    assert "onclick" not in clean
    assert "javascript:" not in clean
    assert "<a" not in clean

    ctx = syn.html_safe_context({
        "USER_NAME": '<img src=x onerror="steal()">',
        "BODY_HTML": "<p>unexpected raw fragment</p>",
        "INTERACTION_STYLE_HTML": "<p>sanitized generated fragment</p>",
    })
    assert ctx["USER_NAME"].startswith("&lt;img")
    assert "onerror=&quot;steal()&quot;" in ctx["USER_NAME"]
    assert ctx["BODY_HTML"] == "&lt;p&gt;unexpected raw fragment&lt;/p&gt;"
    assert ctx["INTERACTION_STYLE_HTML"] == "<p>sanitized generated fragment</p>"


def test_synthesize_profile_html_escapes_untrusted_insight_content(tmp_path: Path):
    insights = _golden_insights()
    insights["interaction_style"]["narrative_html"] = (
        '<p onclick="steal()">Safe <strong>bold</strong>'
        '<img src="x" onerror="steal()">'
        '<script>alert(1)</script>'
        '<a href="javascript:steal()">link</a></p>'
    )
    analysis = tmp_path / "analysis"
    _write_minimal_analysis(analysis, insights)

    result, out = _run_synthesize(tmp_path, analysis, user_name="<b>TestUser</b>")

    assert result.returncode == 0, result.stderr
    profile_html = (out / "PROFILE.html").read_text()
    assert "&lt;b&gt;TestUser&lt;/b&gt;" in profile_html
    assert "<strong>bold</strong>" in profile_html
    assert "<script" not in profile_html
    assert "alert(1)" not in profile_html
    assert "<img" not in profile_html
    assert "onclick" not in profile_html
    assert "javascript:" not in profile_html


def test_profile_template_is_local_only():
    template = (REFERENCES / "profile-template.html").read_text()
    assert "fonts.googleapis.com" not in template
    assert "fonts.gstatic.com" not in template


def test_svg_chart_labels_are_escaped():
    import importlib.util
    charts_path = REFERENCES / "visualization" / "charts.py"
    spec = importlib.util.spec_from_file_location("charts", str(charts_path))
    charts = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(charts)

    svg = charts.word_bars_svg([("<script>alert(1)</script>", 3)], title='Top "words"')
    assert "<script" not in svg
    assert "</script>" not in svg
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in svg
    assert 'aria-label="Top &quot;words&quot;"' in svg


# ---------------------------------------------------------------------------
# Test 3 — Tier 1 end-to-end synth produces rich cards
# ---------------------------------------------------------------------------


def test_synthesize_tier1_uses_insights(tmp_path: Path):
    analysis = tmp_path / "analysis"
    _write_minimal_analysis(analysis, _golden_insights())

    result, out = _run_synthesize(tmp_path, analysis)

    assert result.returncode == 0, result.stderr
    assert "insights tier: 1" in result.stderr
    profile_html = (out / "PROFILE.html").read_text()
    # Cards must contain the golden content
    assert "End-to-end shipping" in profile_html
    assert "Self-healing automation mesh" in profile_html
    assert "Custom skills" in profile_html
    assert "session XYZ truncated" in profile_html
    # Source citations rendered
    assert "source: workflow.md §3" in profile_html


# ---------------------------------------------------------------------------
# Test 4 — Tier 2 fallback (insights absent, rule-based path still works)
# ---------------------------------------------------------------------------


def test_synthesize_tier2_falls_back(tmp_path: Path):
    analysis = tmp_path / "analysis"
    _write_minimal_analysis(analysis)

    result, out = _run_synthesize(tmp_path, analysis)

    assert result.returncode == 0, result.stderr
    assert "insights tier: 3" in result.stderr  # No reports, no insights
    # Pipeline produced HTML without exception
    assert (out / "PROFILE.html").exists()
    assert (out / "PROFILE.md").exists()


# ---------------------------------------------------------------------------
# Test 5 — extract-insights writes 7 files from mocked LLM response
# ---------------------------------------------------------------------------


def test_extract_writes_seven_files(tmp_path: Path):
    reports = tmp_path / "reports"
    reports.mkdir()
    (reports / "orchestration.md").write_text("# Orch\nFake content")
    (reports / "workflow.md").write_text("# Workflow\nFake content")

    analysis = tmp_path / "analysis"
    analysis.mkdir()
    (analysis / "numbers.json").write_text("{}")
    (analysis / "temporal.json").write_text("{}")
    (analysis / "convergence-pairs.json").write_text("{}")
    (analysis / "plan-inventory.json").write_text("{}")
    (analysis / "memory-inventory.json").write_text('{"n_files": 0, "entries": []}')

    insights = tmp_path / "insights"

    mock_response = tmp_path / "mock.json"
    mock_response.write_text(json.dumps(_golden_insights()))

    result = subprocess.run(
        [sys.executable, str(EXTRACT),
         "--reports-dir", str(reports),
         "--analysis-dir", str(analysis),
         "--insights-dir", str(insights),
         "--mock-response-file", str(mock_response),
         "--user-name", "TestUser"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    expected = {
        "project_areas.json", "interaction_style.json", "big_wins.json",
        "friction.json", "suggestions.json", "horizon.json", "fun_ending.json",
    }
    actual = {p.name for p in insights.glob("*.json")}
    assert expected == actual, f"missing: {expected - actual}; extra: {actual - expected}"


def test_extract_does_not_use_sdk_fallback_by_default(tmp_path: Path):
    reports = tmp_path / "reports"
    reports.mkdir()
    (reports / "workflow.md").write_text("# Workflow\nFake content")

    analysis = tmp_path / "analysis"
    analysis.mkdir()
    for name in [
        "numbers.json",
        "temporal.json",
        "convergence-pairs.json",
        "plan-inventory.json",
        "memory-inventory.json",
    ]:
        (analysis / name).write_text("{}")

    result = subprocess.run(
        [sys.executable, str(EXTRACT),
         "--reports-dir", str(reports),
         "--analysis-dir", str(analysis),
         "--insights-dir", str(tmp_path / "insights"),
         "--user-name", "TestUser"],
        capture_output=True,
        text=True,
        env={**os.environ, "PATH": ""},
    )
    assert result.returncode == 2
    assert "Anthropic SDK fallback is disabled" in result.stderr


def test_extract_handles_invalid_json(tmp_path: Path):
    """If the LLM returns invalid JSON, exit nonzero and leave a debug file."""
    reports = tmp_path / "reports"
    reports.mkdir()
    (reports / "x.md").write_text("# x\n")
    analysis = tmp_path / "analysis"
    analysis.mkdir()
    insights = tmp_path / "insights"
    mock = tmp_path / "bad.txt"
    mock.write_text("not even close to JSON{{{ broken")

    result = subprocess.run(
        [sys.executable, str(EXTRACT),
         "--reports-dir", str(reports),
         "--analysis-dir", str(analysis),
         "--insights-dir", str(insights),
         "--mock-response-file", str(mock)],
        capture_output=True, text=True,
    )
    assert result.returncode == 2
    assert "not valid JSON" in result.stderr


def test_extract_handles_empty_reports(tmp_path: Path):
    """No reports/ → exit 0 with warning (Tier 3 fallback)."""
    reports = tmp_path / "reports"
    reports.mkdir()  # exists but empty
    analysis = tmp_path / "analysis"
    analysis.mkdir()
    insights = tmp_path / "insights"

    result = subprocess.run(
        [sys.executable, str(EXTRACT),
         "--reports-dir", str(reports),
         "--analysis-dir", str(analysis),
         "--insights-dir", str(insights)],
        capture_output=True, text=True,
    )
    assert result.returncode == 0
    assert "no .md reports" in result.stderr
    # Should not have written any insights JSON
    assert not insights.exists() or not list(insights.glob("*.json"))


# ---------------------------------------------------------------------------
# Test 8 — Daniel-specific content survives the extraction
# (gated: only runs if /private/ exists, which is Daniel-specific)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not Path("/Users/danielbentes/digital-twin/private/twin-analysis-workflow.md").exists(),
    reason="Daniel's /private/ corpus not available — this gate skips on CI / other users.",
)
def test_daniel_specific_content_in_extraction(tmp_path: Path):
    """After running the extraction on Daniel's v1 reports + rendering, the HTML
    should contain at least 3 verbatim Daniel-specific phrases. This guards
    against future refactors that silently regress to generic templates.

    NOTE: This test does NOT call the live LLM. It expects a pre-existing
    `~/.claude/digital-twin/analysis/insights/` directory populated by the
    bootstrap step. Skip if it doesn't exist yet.
    """
    insights_dir = Path("~/.claude/digital-twin/analysis/insights").expanduser()
    if not insights_dir.exists():
        pytest.skip("bootstrap hasn't been run yet")
    profile = Path("~/.claude/digital-twin/PROFILE.html").expanduser()
    assert profile.exists()
    html = profile.read_text()
    hits = sum(1 for phrase in (
        "Paperclip", "heartbeat", "ship-it", "/flow:",
        "danielbentes", "echo wake", "circuit-breaker",
    ) if phrase.lower() in html.lower())
    assert hits >= 3, (
        f"Only {hits} Daniel-specific phrases in PROFILE.html; "
        "extraction may have regressed to generic content."
    )
