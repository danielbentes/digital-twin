import importlib.util
import json
import subprocess
import sys
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = PLUGIN_ROOT / "skills" / "digital-twin" / "scripts"
SYNTH = SCRIPTS / "synthesize.py"
EXTRACT_TWIN_SPEC = SCRIPTS / "extract-twin-spec.py"
EVAL = SCRIPTS / "evaluate-twin.py"


def _golden_twin_spec() -> dict:
    rules = [
        {
            "rank": i,
            "title": title,
            "rule": rule,
            "evidence": "quality.md §7",
        }
        for i, (title, rule) in enumerate(
            [
                ("No fake completion", "Never claim done without fresh verification evidence."),
                ("No unnecessary questions", "Decide discoverable operational details yourself."),
                ("No symptom patching", "Root-cause before implementing a fix."),
                ("No scope creep", "Keep side findings out of the active issue."),
                ("No stale branch facts", "Fetch/read current state before branch claims."),
            ],
            1,
        )
    ]
    return {
        "identity": [
            {"fact": "Daniel operates Claude Code as an implementation orchestrator.", "evidence": "orchestration.md §1"},
            {"fact": "He expects autonomous decisions on discoverable facts.", "evidence": "encoded-rules.md §1"},
            {"fact": "He treats verification evidence as mandatory before ship claims.", "evidence": "quality.md §6"},
        ],
        "operating_model": {
            "default_stance": "Ground in the repo, decide operational details, verify before claiming done.",
            "autonomy_level": "High for reversible/discoverable work; explicit gates for destructive or scope-changing actions.",
            "planning_threshold": "Plan non-trivial work before editing; keep single-PR work surgical.",
            "quality_bar": "Production-ready, root-caused, verified, and reviewable.",
            "evidence": "workflow.md canonical pipeline",
        },
        "decision_policy": {
            "decide_alone": ["Read files", "Run safe checks", "Pick local conventions from evidence"],
            "escalate": ["Merge/release/publish", "Destructive commands", "Scope changes"],
            "default_assumption": "Act on discoverable facts instead of asking.",
            "evidence": "encoded-rules.md §1",
        },
        "delegation_policy": {
            "parallel_triggers": ["Independent backend/frontend/docs analysis", "Comprehensive review across multiple areas"],
            "serial_triggers": ["Pushback recovery", "Tightly coupled implementation"],
            "worktree_policy": "Use isolated worktrees for independent implementation agents.",
            "clean_context_review_triggers": ["Confidence loss", "High-stakes review", "Claims need adversarial check"],
            "evidence": "orchestration.md §1",
        },
        "workflow_policy": {
            "stages": [
                {"name": "Intake", "trigger": "Issue or repo task", "actions": ["Read local instructions", "Find issue/branch context"], "done_when": "Scope and conventions are known", "evidence": "workflow.md §1"},
                {"name": "Plan", "trigger": "Non-trivial work", "actions": ["Write Context/Approach/Verification/Out of scope"], "done_when": "Plan is executable", "evidence": "planning-style.md §8"},
                {"name": "Verify", "trigger": "Before completion", "actions": ["Run tests/type checks/runtime checks"], "done_when": "Fresh evidence exists", "evidence": "quality.md §6"},
            ],
            "evidence": "workflow.md",
        },
        "verification_policy": {
            "completion_claim_requires": ["Fresh test/check output", "Runtime artifact for UI or integration behavior"],
            "fresh_evidence_examples": ["pytest output", "type check output", "browser screenshot", "CI green link"],
            "forbidden_claims": ["No done claims from stale memory", "No done claims from intent alone"],
            "evidence": "quality.md §6",
        },
        "recovery_policy": {
            "pushback_signals": ["wait", "stop", "actually", "but", "not good enough"],
            "first_response_template": "Fair pushback.\n\n| What I claimed | What is actually true |\n| --- | --- |\n| ... | ... |\n\nShould I correct this now?",
            "required_steps": ["Concede", "Name the gap", "Show evidence", "Ask one binary question"],
            "long_tail_escalation": "After repeated mismatch, stop and ask for a concrete decision.",
            "evidence": "failure-recovery.md §8",
        },
        "voice_policy": {
            "default_register": "Terse, direct, evidence-first.",
            "target_length": "Short for approvals; longer only for plans and gap analysis.",
            "do": ["Use file/command evidence", "State decisions plainly"],
            "avoid": ["Filler", "emojis", "recapping the user's prompt"],
            "examples": ["Implemented and verified with fresh test output."],
            "evidence": "quality.md §4",
        },
        "project_routing": {
            "unknown_project_behavior": "Read `CLAUDE.md`, `.claude/rules/`, and `.decisions/`; ask only if conventions remain ambiguous.",
            "projects": [
                {"slug": "-Users-danielbentes-grounded-harness", "behavior": "Require rigorous verification and decision journals.", "evidence": "encoded-rules.md project glossary"}
            ],
        },
        "never_rules": rules,
        "always_rules": [
            {**r, "title": r["title"].replace("No ", ""), "rule": r["rule"].replace("Never ", "Always ")}
            for r in rules
        ],
        "examples": {
            "approved_turn": "Implemented and verified with fresh test output.",
            "plan_turn": "Context / Approach / Verification / Out of scope.",
            "delegation_turn": "Dispatch parallel agents for independent areas, then consolidate.",
            "recovery_turn": "Fair pushback. Here is the gap table and one binary decision.",
        },
        "evidence": {"workflow": "workflow.md", "quality": "quality.md"},
    }


def _write_minimal_analysis(analysis: Path, include_spec: bool = True) -> None:
    analysis.mkdir(parents=True)
    (analysis / "numbers.json").write_text(json.dumps({
        "n_prompts": 100,
        "n_projects": 1,
        "approval_count": 10,
        "pushback_count": 2,
        "slash_share_pct": 20,
        "avg_prompt_length_chars": 100,
        "median_prompt_length_chars": 50,
        "p90_prompt_length_chars": 300,
        "top_approval_words": [["proceed", 5]],
        "top_pushback_words": [["wait", 2]],
        "top_first_words": [],
        "per_project_top20": [],
    }))
    (analysis / "temporal.json").write_text(json.dumps({
        "hour_histogram": {},
        "dow_histogram": {},
        "recovery_cycles": {},
        "vocab_drift": {},
    }))
    (analysis / "memory-inventory.json").write_text('{"n_files": 0, "entries": []}')
    (analysis / "plan-inventory.json").write_text('{"n_plans": 0, "archetypes": {}}')
    (analysis / "convergence-pairs.json").write_text(json.dumps({
        "n_pairs": 10,
        "counts": {"approval": 5, "neutral": 5},
        "first_word_top": {"approval": [["proceed", 5]], "explicit_pushback": [["wait", 2]]},
    }))
    if include_spec:
        (analysis / "twin-spec.json").write_text(json.dumps(_golden_twin_spec()))


def test_extract_twin_spec_mock_writes_valid_spec(tmp_path: Path):
    reports = tmp_path / "reports"
    reports.mkdir()
    (reports / "workflow.md").write_text("# Workflow\nEvidence")
    analysis = tmp_path / "analysis"
    _write_minimal_analysis(analysis, include_spec=False)
    mock = tmp_path / "mock.json"
    mock.write_text(json.dumps(_golden_twin_spec()))
    out = analysis / "twin-spec.json"

    result = subprocess.run(
        [
            sys.executable,
            str(EXTRACT_TWIN_SPEC),
            "--analysis-dir",
            str(analysis),
            "--reports-dir",
            str(reports),
            "--out-json",
            str(out),
            "--mock-response-file",
            str(mock),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(out.read_text())["operating_model"]["default_stance"]


def test_synthesize_uses_twin_spec_for_compact_agent_and_rules(tmp_path: Path):
    analysis = tmp_path / "analysis"
    _write_minimal_analysis(analysis, include_spec=True)
    out = tmp_path / "out"
    agents = tmp_path / "agents"
    out.mkdir()
    agents.mkdir()

    result = subprocess.run(
        [
            sys.executable,
            str(SYNTH),
            "--analysis",
            str(analysis),
            "--reports",
            str(tmp_path / "empty-reports"),
            "--out",
            str(out),
            "--agents-dir",
            str(agents),
            "--user-name",
            "Daniel",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    twin = (agents / "twin.md").read_text()
    assert "Behavioral spec complete" in twin
    assert "Decision Policy" in twin
    assert "Verification Policy" in twin
    assert "Recovery Policy" in twin
    assert "See PROFILE.md" not in twin
    assert "The 45 encoded rules" not in twin
    assert "{{" not in twin
    assert "_TBD_" not in twin
    assert len(twin.splitlines()) < 260

    for name in ("preferences.md", "workflows.md", "verification.md", "recovery.md"):
        assert (out / "rules" / name).exists()
    patch = (out / "CLAUDE-md-patch.md").read_text()
    assert "@~/.claude/digital-twin/rules/preferences.md" in patch


def test_synthesize_degraded_twin_is_explicit(tmp_path: Path):
    analysis = tmp_path / "analysis"
    _write_minimal_analysis(analysis, include_spec=False)
    out = tmp_path / "out"
    agents = tmp_path / "agents"
    out.mkdir()
    agents.mkdir()
    result = subprocess.run(
        [
            sys.executable,
            str(SYNTH),
            "--analysis",
            str(analysis),
            "--out",
            str(out),
            "--agents-dir",
            str(agents),
            "--user-name",
            "Daniel",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    twin = (agents / "twin.md").read_text()
    assert "INCOMPLETE BEHAVIORAL SPEC" in twin


def test_eval_harness_scores_twin_above_generic_fixture():
    spec = importlib.util.spec_from_file_location("evaluate_twin", str(EVAL))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    cases = json.loads((PLUGIN_ROOT / "tests" / "fixtures" / "eval" / "heldout_cases.json").read_text())
    result = mod.evaluate(cases)
    assert result["twin_win_rate"] >= 0.8
    assert result["pushback_trigger_hit_rate"] is None or result["pushback_trigger_hit_rate"] >= 0.7
