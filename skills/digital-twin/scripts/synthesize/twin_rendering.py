"""Twin Markdown rendering."""
from __future__ import annotations

from .shared import bulleted_list, numbered_list
from .spec_core import _spec_list, _spec_text


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


def render_constitution(spec: dict) -> str:
    pol = spec.get("constitution") or {}
    parts = []
    values = []
    for value in pol.get("values") or []:
        if not isinstance(value, dict):
            continue
        name = _spec_text(value.get("name"))
        principle = _spec_text(value.get("principle"))
        because = _spec_text(value.get("because"))
        tradeoffs = _spec_text(value.get("tradeoffs"))
        evidence = _spec_text(value.get("evidence"))
        if not (name or principle):
            continue
        line = f"**{name}** — {principle}" if name and principle else name or principle
        details = []
        if because:
            details.append(f"Because: {because}")
        if tradeoffs:
            details.append(f"Tradeoffs: {tradeoffs}")
        if evidence:
            details.append(f"Evidence: {evidence}")
        if details:
            line += "\n  " + "\n  ".join(f"- {d}" for d in details)
        values.append(line)
    if values:
        parts.append("Values:\n" + numbered_list(values))

    judgments = []
    for rule in pol.get("judgment_rules") or []:
        if not isinstance(rule, dict):
            continue
        situation = _spec_text(rule.get("situation"))
        reasoning = _spec_text(rule.get("reasoning"))
        preferred = _spec_text(rule.get("preferred_action"))
        avoid = _spec_text(rule.get("avoid"))
        evidence = _spec_text(rule.get("evidence"))
        if not situation:
            continue
        block = [f"**{situation}**"]
        if reasoning:
            block.append(f"Reasoning: {reasoning}")
        if preferred:
            block.append(f"Preferred action: {preferred}")
        if avoid:
            block.append(f"Avoid: {avoid}")
        if evidence:
            block.append(f"Evidence: {evidence}")
        judgments.append("\n  ".join(block))
    if judgments:
        parts.append("Judgment rules:\n" + numbered_list(judgments))
    if pol.get("evidence"):
        parts.append(f"Evidence: {pol.get('evidence')}")
    return "\n\n".join(parts) if parts else "_No constitution extracted._"


def render_substitution_contract(spec: dict) -> str:
    pol = spec.get("substitution_contract") or {}
    parts = []
    role = _spec_text(pol.get("role"))
    if role:
        parts.append(f"Role: {role}")
    for title, key in (
        ("Autonomous authority", "autonomous_authority"),
        ("Reserved for the real user", "user_reserved_authority"),
        ("Delegation authority", "delegation_authority"),
        ("Boundaries", "boundaries"),
    ):
        vals = _spec_list(pol.get(key))
        if vals:
            parts.append(f"{title}:\n" + bulleted_list(vals))
    stance = _spec_text(pol.get("supervision_stance"))
    if stance:
        parts.append(f"Supervision stance: {stance}")
    if pol.get("evidence"):
        parts.append(f"Evidence: {pol.get('evidence')}")
    return "\n\n".join(parts) if parts else "_No substitution contract extracted._"


def render_trust_policy(spec: dict) -> str:
    pol = spec.get("trust_policy") or {}
    parts = []
    for title, key in (
        ("Trust agent output when", "trust_signals"),
        ("Withhold trust when", "distrust_signals"),
        ("Evidence requirements", "evidence_requirements"),
        ("Interrupt or redirect when", "interruption_triggers"),
    ):
        vals = _spec_list(pol.get(key))
        if vals:
            parts.append(f"{title}:\n" + bulleted_list(vals))
    threshold = _spec_text(pol.get("escalation_threshold"))
    if threshold:
        parts.append(f"Escalation threshold: {threshold}")
    if pol.get("evidence"):
        parts.append(f"Evidence: {pol.get('evidence')}")
    return "\n\n".join(parts) if parts else "_No trust policy extracted._"


def render_agent_supervision_policy(spec: dict) -> str:
    pol = spec.get("agent_supervision_policy") or {}
    parts = []
    for title, key in (
        ("Brief agents with", "briefing_requirements"),
        ("Review agent work by", "review_actions"),
        ("Correct agents by", "correction_actions"),
    ):
        vals = _spec_list(pol.get(key))
        if vals:
            parts.append(f"{title}:\n" + bulleted_list(vals))
    standard = _spec_text(pol.get("completion_standard"))
    if standard:
        parts.append(f"Completion standard: {standard}")
    if pol.get("evidence"):
        parts.append(f"Evidence: {pol.get('evidence')}")
    return "\n\n".join(parts) if parts else "_No agent supervision policy extracted._"


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


def render_rule_set(
    spec: dict,
    key: str,
    limit: int | None = None,
    detail_mode: str = "full",
) -> str:
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
        details = []
        all_detail_fields: tuple[tuple[str, str], ...] = (
            ("Principle", "principle"),
            ("Because", "because"),
            ("Applies when", "applies_when"),
            ("Failure mode", "failure_mode"),
            ("Good example", "example_good"),
            ("Bad example", "example_bad"),
        )
        detail_fields: tuple[tuple[str, str], ...]
        if detail_mode == "principle":
            detail_fields = all_detail_fields[:2]
        elif detail_mode == "none":
            detail_fields = ()
        else:
            detail_fields = all_detail_fields
        for label, detail_key in detail_fields:
            val = _spec_text(rule.get(detail_key))
            if val:
                details.append(f"{label}: {val}")
        if ev and detail_mode == "full":
            details.append(f"Evidence: {ev}")
        if details:
            line += "\n  " + "\n  ".join(f"- {d}" for d in details)
        rows.append(line)
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


def render_twin_context(
    spec: dict,
    complete: bool,
    args,
    compatibility_defaults: bool = False,
) -> dict:
    if not complete:
        status = "INCOMPLETE BEHAVIORAL SPEC: this is a degraded fallback. Regenerate `analysis/twin-spec.json` before treating this as a replacement twin."
    elif compatibility_defaults:
        status = "Behavioral spec valid via v0.3 → v0.4 compatibility migration with compatibility-derived substitution defaults. Refresh `analysis/twin-spec.json` before treating this as full delegate authority."
    else:
        status = "Behavioral spec complete. Use this as the operating contract."
    return {
        "TWIN_SPEC_STATUS": status,
        "IDENTITY_FACTS": render_identity(spec),
        "CONSTITUTION_SECTION": render_constitution(spec),
        "SUBSTITUTION_CONTRACT_SECTION": render_substitution_contract(spec),
        "TRUST_POLICY_SECTION": render_trust_policy(spec),
        "AGENT_SUPERVISION_SECTION": render_agent_supervision_policy(spec),
        "OPERATING_MODEL_SECTION": render_operating_model(spec),
        "DECISION_POLICY_SECTION": render_decision_policy(spec),
        "DELEGATION_POLICY_SECTION": render_delegation_policy(spec),
        "WORKFLOW_POLICY_SECTION": render_workflow_policy(spec),
        "VERIFICATION_POLICY_SECTION": render_verification_policy(spec),
        "RECOVERY_POLICY_SECTION": render_recovery_policy(spec),
        "VOICE_POLICY_SECTION": render_voice_policy(spec),
        "PROJECT_ROUTING_SECTION": render_project_routing(spec),
        "NEVER_RULES_TOP": render_rule_set(spec, "never_rules", limit=8, detail_mode="principle"),
        "ALWAYS_RULES_TOP": render_rule_set(spec, "always_rules", limit=8, detail_mode="principle"),
        "EXAMPLES_SECTION": render_examples(spec),
        "EVIDENCE_SECTION": render_evidence_map(spec),
        "RULES_REFERENCE_SECTION": (
            "Generated rule files live under `~/.claude/digital-twin/rules/`. "
            "Install them through `CLAUDE-md-patch.md` or symlink them into `~/.claude/rules/`."
        ),
        "DEFAULT_REGISTER": _spec_text((spec.get("voice_policy") or {}).get("default_register"), "concise, direct"),
        "TARGET_TWIN_REPLY_LEN": str(args.target_twin_reply_len),
    }
