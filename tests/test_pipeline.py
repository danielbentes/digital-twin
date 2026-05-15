"""
End-to-end smoke test of the digital-twin pipeline on a synthetic corpus.

This test runs every script in sequence and asserts the artifacts are produced
with non-trivial content. It does NOT exercise the deep-read agents (those
require live Claude API calls and are out of scope for unit tests).
"""
import json
import importlib.util
import subprocess
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "skills" / "digital-twin" / "scripts"


def run(*args, **kwargs):
    """Run a subprocess and surface its output on failure."""
    result = subprocess.run(args, capture_output=True, text=True, **kwargs)
    if result.returncode != 0:
        raise AssertionError(
            f"Command failed: {' '.join(args)}\n"
            f"--- stdout ---\n{result.stdout}\n"
            f"--- stderr ---\n{result.stderr}\n"
        )
    return result


def test_full_pipeline(synthetic_corpus_dir, tmp_path):
    out = tmp_path / "analysis"
    out.mkdir()

    # 1. Extract
    run(
        sys.executable, str(SCRIPTS / "extract-corpus.py"),
        "--source", str(synthetic_corpus_dir),
        "--out", str(out),
    )
    assert (out / "corpus.jsonl").exists()
    assert (out / "timestamped.jsonl").exists()
    summary = json.loads((out / "_summary.json").read_text())
    assert summary["n_prompts_total"] > 0, "extractor produced no prompts"
    assert summary["n_session_files"] == 3

    # 2. Quantitative
    run(
        sys.executable, str(SCRIPTS / "quantitative.py"),
        "--corpus", str(out / "corpus.jsonl"),
        "--out-json", str(out / "numbers.json"),
        "--out-md", str(out / "numbers.md"),
    )
    numbers = json.loads((out / "numbers.json").read_text())
    assert numbers["n_prompts"] > 0
    assert 0 <= numbers.get("slash_share_pct", 0) <= 100, (
        "slash share must be a valid percentage"
    )

    # 3. Temporal
    run(
        sys.executable, str(SCRIPTS / "temporal.py"),
        "--timestamped", str(out / "timestamped.jsonl"),
        "--out-json", str(out / "temporal.json"),
        "--out-md", str(out / "temporal.md"),
    )
    temporal = json.loads((out / "temporal.json").read_text())
    assert "hour_histogram" in temporal
    assert "dow_histogram" in temporal

    # 4. Memory inventory
    run(
        sys.executable, str(SCRIPTS / "memory-inventory.py"),
        "--source", str(synthetic_corpus_dir),
        "--out-json", str(out / "memory-inventory.json"),
        "--out-md", str(out / "rules.md"),
    )
    mem = json.loads((out / "memory-inventory.json").read_text())
    assert mem["n_files"] == 3, "expected 3 synthetic memory files"

    # 5. Convergence pairs
    run(
        sys.executable, str(SCRIPTS / "assistant-turn-mining.py"),
        "--source", str(synthetic_corpus_dir),
        "--out-json", str(out / "convergence-pairs.json"),
        "--out-md", str(out / "pushback-triggers.md"),
    )
    conv = json.loads((out / "convergence-pairs.json").read_text())
    assert conv["n_pairs"] > 0

    # 6. Synthesize
    out_synth = tmp_path / "out"
    agents = tmp_path / "agents"
    out_synth.mkdir()
    agents.mkdir()
    run(
        sys.executable, str(SCRIPTS / "synthesize.py"),
        "--analysis", str(out),
        "--out", str(out_synth),
        "--agents-dir", str(agents),
        "--user-name", "TestUser",
        "--profile-version", "test",
    )
    profile_md = out_synth / "PROFILE.md"
    profile_html = out_synth / "PROFILE.html"
    twin = agents / "twin.md"
    assert profile_md.exists(), "PROFILE.md was not written"
    assert profile_html.exists(), "PROFILE.html was not written"
    assert twin.exists(), "twin.md was not written"
    assert profile_md.read_text().count("# TestUser") >= 1
    assert "| Sessions | **3** |" in profile_md.read_text(), (
        "PROFILE.md should show session count from corpus summary"
    )
    assert "<svg" in profile_html.read_text(), "HTML should contain SVG charts"


def test_pushback_detector_emits_canonical_format(synthetic_corpus_dir, tmp_path):
    out_dir = tmp_path / "proposed"
    out_dir.mkdir()
    state = tmp_path / ".state.json"
    run(
        sys.executable, str(SCRIPTS / "pushback-detector.py"),
        "--source", str(synthetic_corpus_dir),
        "--out-dir", str(out_dir),
        "--state-file", str(state),
        "--reset-state",
        "--max-proposals", "5",
        "--min-confidence", "0.4",
    )
    # Either 0 or N proposals; if N>0, each must be canonical-format
    proposals = list(out_dir.glob("*.md"))
    for p in proposals:
        txt = p.read_text()
        assert txt.startswith("---\n"), f"{p.name} missing frontmatter"
        assert "name:" in txt
        assert "type: feedback" in txt
        assert "## Evidence (from session)" in txt


def test_pushback_detector_idempotent(synthetic_corpus_dir, tmp_path):
    """Running twice should not emit duplicate proposals."""
    out_dir = tmp_path / "proposed"
    out_dir.mkdir()
    state = tmp_path / ".state.json"

    common = [
        sys.executable, str(SCRIPTS / "pushback-detector.py"),
        "--source", str(synthetic_corpus_dir),
        "--out-dir", str(out_dir),
        "--state-file", str(state),
        "--max-proposals", "5",
    ]
    run(*common, "--reset-state")
    first_count = len(list(out_dir.glob("*.md")))
    # Re-run without resetting state — should produce zero new proposals
    run(*common)
    second_count = len(list(out_dir.glob("*.md")))
    assert second_count == first_count, "second run produced extra proposals"


def test_chart_module_pure():
    """charts.py must be importable in isolation with no side effects."""
    charts_path = (
        Path(__file__).resolve().parent.parent
        / "skills" / "digital-twin" / "references" / "visualization" / "charts.py"
    )
    spec = importlib.util.spec_from_file_location("charts", charts_path)
    assert spec is not None and spec.loader is not None
    c = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(c)
    # Must produce non-empty SVG for empty-ish data without crashing
    assert "svg" in c.hour_heatmap_svg([1] * 24, peak_hour=12)
    assert "<table" not in c.hour_heatmap_svg([1] * 24)  # no table fallback
    assert c.convergence_donut_svg({}).startswith("<p>")  # graceful
