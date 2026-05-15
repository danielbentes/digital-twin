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
            "principle": principle,
            "because": because,
            "applies_when": "When acting as Daniel's operational delegate.",
            "failure_mode": failure,
            "example_good": "Decide from repo evidence, brief agents clearly, and demand fresh verification.",
            "example_bad": "Ask generic questions or accept unevidenced agent claims.",
            "evidence": "quality.md §7",
        }
        for i, (title, rule, principle, because, failure) in enumerate(
            [
                ("No fake completion", "Never claim done without fresh verification evidence.", "Trust requires artifacts.", "Daniel treats completion claims as contracts.", "Agent claims done from intent alone."),
                ("No unnecessary questions", "Decide discoverable operational details yourself.", "Substitution means making user-like operational calls.", "The corpus shows pushback on questions the agent could answer.", "Agent stalls delegation with avoidable questions."),
                ("No symptom patching", "Root-cause before implementing a fix.", "Fix judgment failures, not visible symptoms.", "Daniel pushes agents back toward root cause.", "Agent ships a patch without diagnosis."),
                ("No scope creep", "Keep side findings out of the active issue.", "Minimize blast radius.", "Unrelated work dilutes review and verification.", "Agent expands delegated scope without approval."),
                ("No stale branch facts", "Fetch/read current state before branch claims.", "Current evidence beats memory.", "Branch state changes across sessions.", "Agent directs work from stale assumptions."),
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
        "constitution": {
            "values": [
                {
                    "name": "Act as the delegate",
                    "principle": "Run the work as Daniel would when he is absent.",
                    "because": "The twin's purpose is substitution, not generic assistance.",
                    "tradeoffs": "Proceed on reversible, discoverable work; escalate reserved authority.",
                    "evidence": "orchestration.md §1",
                },
                {
                    "name": "Evidence earns trust",
                    "principle": "Accept agent work only when claims are backed by fresh artifacts.",
                    "because": "Daniel rejects unevidenced completion claims.",
                    "tradeoffs": "Slow down to verify before accepting delegated work.",
                    "evidence": "quality.md §6",
                },
                {
                    "name": "Constrain blast radius",
                    "principle": "Keep delegated work inside the active issue unless scope is explicitly expanded.",
                    "because": "Daniel pushes back on unrelated edits.",
                    "tradeoffs": "File follow-ups instead of mixing concerns.",
                    "evidence": "quality.md §2",
                },
            ],
            "judgment_rules": [
                {
                    "situation": "An agent asks for discoverable facts",
                    "reasoning": "Daniel expects the operator to inspect local evidence first.",
                    "preferred_action": "Redirect the agent to read the relevant files and return evidence.",
                    "avoid": "Forwarding avoidable questions to Daniel.",
                    "evidence": "encoded-rules.md §1",
                },
                {
                    "situation": "Multiple agents disagree",
                    "reasoning": "Daniel resolves by evidence quality, not by majority vote.",
                    "preferred_action": "Compare file citations, test output, and runtime artifacts.",
                    "avoid": "Choosing the most confident-sounding report.",
                    "evidence": "orchestration.md §4",
                },
                {
                    "situation": "Agent output expands scope",
                    "reasoning": "Scope changes need explicit authority.",
                    "preferred_action": "Narrow the plan or escalate the scope change.",
                    "avoid": "Letting adjacent cleanup enter the delegated task.",
                    "evidence": "quality.md §2",
                },
            ],
            "evidence": "reports",
        },
        "substitution_contract": {
            "role": "Act as Daniel's operational delegate for orchestrating other agents.",
            "autonomous_authority": ["Brief agents", "Review agent output", "Run reversible checks"],
            "user_reserved_authority": ["Merge/release/publish", "Destructive commands", "Scope changes"],
            "delegation_authority": ["Dispatch independent read-only agents", "Split work by non-overlapping ownership"],
            "supervision_stance": "Challenge weak agent plans and demand evidence before accepting work.",
            "boundaries": ["Do not impersonate Daniel for irreversible external commitments."],
            "evidence": "orchestration.md §1",
        },
        "trust_policy": {
            "trust_signals": ["Fresh test output", "File citations", "Runtime artifact"],
            "distrust_signals": ["No evidence", "Scope drift", "Stale branch claim"],
            "evidence_requirements": ["Artifact-backed claim before accepting delegated completion"],
            "interruption_triggers": ["Agent expands scope", "Agent lacks evidence", "Agent asks avoidable questions"],
            "escalation_threshold": "Escalate when authority is reserved for Daniel or evidence is weak.",
            "evidence": "quality.md §6",
        },
        "agent_supervision_policy": {
            "briefing_requirements": ["Scope", "Expected evidence", "Output shape"],
            "review_actions": ["Check file citations", "Check verification output", "Challenge scope drift"],
            "correction_actions": ["Name failed judgment", "Redirect to root cause", "Require updated evidence"],
            "completion_standard": "Accept agent work only when it meets Daniel's verification bar.",
            "evidence": "failure-recovery.md §8",
        },
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
            {**r, "title": str(r["title"]).replace("No ", ""), "rule": str(r["rule"]).replace("Never ", "Always ")}
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


def _invalid_nested_twin_spec() -> dict:
    spec = _golden_twin_spec()
    spec["verification_policy"]["completion_claim_requires"] = "fresh tests"
    spec["workflow_policy"]["stages"][0]["actions"] = "read files"
    spec["always_rules"][0]["rank"] = 0
    return spec


def _missing_substitution_spec() -> dict:
    spec = _golden_twin_spec()
    del spec["substitution_contract"]
    return spec


def _empty_substitution_spec() -> dict:
    spec = _golden_twin_spec()
    spec["substitution_contract"]["autonomous_authority"] = []
    spec["trust_policy"]["trust_signals"] = []
    spec["agent_supervision_policy"]["briefing_requirements"] = []
    return spec


def _legacy_twin_spec() -> dict:
    spec = _golden_twin_spec()
    for key in (
        "constitution",
        "substitution_contract",
        "trust_policy",
        "agent_supervision_policy",
    ):
        del spec[key]
    return spec


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


def test_extract_twin_spec_rejects_nested_schema_errors(tmp_path: Path):
    reports = tmp_path / "reports"
    reports.mkdir()
    (reports / "workflow.md").write_text("# Workflow\nEvidence")
    analysis = tmp_path / "analysis"
    _write_minimal_analysis(analysis, include_spec=False)
    mock = tmp_path / "mock-invalid.json"
    mock.write_text(json.dumps(_invalid_nested_twin_spec()))
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
    assert result.returncode == 2
    assert "failed validation" in result.stderr
    assert not out.exists()
    assert (analysis / "twin-spec.invalid.json").exists()


def test_extract_twin_spec_rejects_missing_substitution_contract(tmp_path: Path):
    reports = tmp_path / "reports"
    reports.mkdir()
    (reports / "workflow.md").write_text("# Workflow\nEvidence")
    analysis = tmp_path / "analysis"
    _write_minimal_analysis(analysis, include_spec=False)
    mock = tmp_path / "mock-invalid-missing-substitution.json"
    mock.write_text(json.dumps(_missing_substitution_spec()))
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
    assert result.returncode == 2
    assert "$.substitution_contract: missing required field" in result.stderr
    assert not out.exists()


def test_extract_twin_spec_rejects_empty_substitution_policies(tmp_path: Path):
    reports = tmp_path / "reports"
    reports.mkdir()
    (reports / "workflow.md").write_text("# Workflow\nEvidence")
    analysis = tmp_path / "analysis"
    _write_minimal_analysis(analysis, include_spec=False)
    mock = tmp_path / "mock-invalid-empty-substitution.json"
    mock.write_text(json.dumps(_empty_substitution_spec()))
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
    assert result.returncode == 2
    assert "$.substitution_contract.autonomous_authority: expected at least 1 items" in result.stderr
    assert "$.trust_policy.trust_signals: expected at least 1 items" in result.stderr
    assert "$.agent_supervision_policy.briefing_requirements: expected at least 1 items" in result.stderr
    assert not out.exists()


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
    assert "Substitution Contract" in twin
    assert "Constitution" in twin
    assert "Trust Policy" in twin
    assert "Agent Supervision" in twin
    assert "Decision Policy" in twin
    assert "Verification Policy" in twin
    assert "Recovery Policy" in twin
    assert "See PROFILE.md" not in twin
    assert "The 45 encoded rules" not in twin
    assert "{{" not in twin
    assert "_TBD_" not in twin
    assert len(twin.splitlines()) < 380

    assert "Principle: Trust requires artifacts." in twin

    for name in ("substitution.md", "preferences.md", "workflows.md", "verification.md", "recovery.md"):
        assert (out / "rules" / name).exists()
    substitution = (out / "rules" / "substitution.md").read_text()
    assert "Act as Daniel's operational delegate" in substitution
    assert "Trust Policy" in substitution
    patch = (out / "CLAUDE-md-patch.md").read_text()
    assert "@~/.claude/digital-twin/rules/substitution.md" in patch
    assert "@~/.claude/digital-twin/rules/preferences.md" in patch


def test_synthesize_backfills_legacy_twin_spec_with_compatibility_status(tmp_path: Path):
    analysis = tmp_path / "analysis"
    _write_minimal_analysis(analysis, include_spec=False)
    (analysis / "twin-spec.json").write_text(json.dumps(_legacy_twin_spec()))
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
    assert "compatibility-derived substitution defaults" in twin
    assert "Behavioral spec complete. Use this as the operating contract." not in twin
    assert "Substitution Contract" in twin
    assert "derived from legacy twin-spec fields" in twin
    assert (out / "rules" / "substitution.md").exists()
    meta = json.loads((out / "_synthesis.json").read_text())
    assert meta["had_twin_spec"] is True
    assert meta["had_compatibility_defaults"] is True


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
    assert "do not claim to substitute" in twin.lower()


def test_synthesize_invalid_twin_spec_degrades(tmp_path: Path):
    analysis = tmp_path / "analysis"
    _write_minimal_analysis(analysis, include_spec=False)
    (analysis / "twin-spec.json").write_text(json.dumps(_invalid_nested_twin_spec()))
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
    assert "failed schema validation" in result.stderr
    twin = (agents / "twin.md").read_text()
    assert "INCOMPLETE BEHAVIORAL SPEC" in twin
    assert "Behavioral spec complete" not in twin


def test_eval_harness_scores_twin_above_generic_fixture():
    spec = importlib.util.spec_from_file_location("evaluate_twin", str(EVAL))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    cases = json.loads((PLUGIN_ROOT / "tests" / "fixtures" / "eval" / "heldout_cases.json").read_text())
    result = mod.evaluate(cases)
    assert result["twin_win_rate"] >= 0.8
    assert result["pushback_trigger_hit_rate"] is None or result["pushback_trigger_hit_rate"] >= 0.7
    assert result["category_scores"]["agent-supervision"] >= 0.8
    assert result["category_scores"]["authority"] >= 0.8
    assert result["category_scores"]["trust"] >= 0.8


def test_eval_harness_scores_concepts_and_forbidden_phrases():
    spec = importlib.util.spec_from_file_location("evaluate_twin", str(EVAL))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    expected = {
        "concept_groups": [
            ["scope", "out of scope"],
            ["evidence", "file"],
            ["redirect", "narrow", "revise"],
        ],
        "forbidden_phrases": ["sounds good"],
    }

    good = mod.score_response(
        "Redirect the scope: keep the refactor out of scope, cite file evidence, "
        "and revise the plan to narrow the fix.",
        expected,
    )
    missing_concept = mod.score_response("Redirect the scope and revise the plan.", expected)
    forbidden = mod.score_response(
        "Sounds good. Redirect the scope, keep it out of scope, cite file evidence, "
        "and narrow the plan.",
        expected,
    )

    assert good["concept_coverage"] == 1
    assert good["forbidden_match"] == 1
    assert missing_concept["concept_coverage"] == 0
    assert forbidden["forbidden_match"] == 0
