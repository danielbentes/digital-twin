"""Final rule and artifact writers."""
from __future__ import annotations

import datetime as dt
import json

from pathlib import Path

from .twin_rendering import (
    render_agent_supervision_policy,
    render_constitution,
    render_decision_policy,
    render_delegation_policy,
    render_identity,
    render_operating_model,
    render_project_routing,
    render_recovery_policy,
    render_rule_set,
    render_substitution_contract,
    render_trust_policy,
    render_verification_policy,
    render_voice_policy,
    render_workflow_policy,
)


def write_rules_files(out: Path, spec: dict, generated_date: str) -> dict[str, Path]:
    rules_dir = out / "rules"
    rules_dir.mkdir(parents=True, exist_ok=True)
    files = {
        "substitution": rules_dir / "substitution.md",
        "preferences": rules_dir / "preferences.md",
        "workflows": rules_dir / "workflows.md",
        "verification": rules_dir / "verification.md",
        "recovery": rules_dir / "recovery.md",
    }
    files["substitution"].write_text(
        "\n".join([
            "# Twin Substitution Contract",
            "",
            f"_Generated {generated_date} from behavioral twin spec._",
            "",
            "## Substitution Contract",
            render_substitution_contract(spec),
            "",
            "## Constitution",
            render_constitution(spec),
            "",
            "## Trust Policy",
            render_trust_policy(spec),
            "",
            "## Agent Supervision",
            render_agent_supervision_policy(spec),
            "",
        ]),
        encoding="utf-8",
    )
    files["preferences"].write_text(
        "\n".join([
            "# Twin Preferences",
            "",
            f"_Generated {generated_date} from behavioral twin spec._",
            "",
            "## Constitution",
            render_constitution(spec),
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
            "## Substitution Contract",
            render_substitution_contract(spec),
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
            "## Agent Supervision",
            render_agent_supervision_policy(spec),
            "",
            "## Trust Policy",
            render_trust_policy(spec),
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


def write_final_outputs(
    *,
    out: Path,
    agents_dir: Path,
    templates: Path,
    ctx: dict,
    args,
    convergence: dict,
    canonical: str,
    generated_rule_files: dict[str, Path],
    numbers: dict,
    n_session_files,
    memory: dict,
    plan_inv: dict,
    pr_stats,
    twin_spec_complete: bool,
    twin_spec_compat_defaults: bool,
    load_text,
    fill,
    html_safe_context,
    placeholder_re,
) -> int:
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
        "n_session_files": n_session_files if n_session_files != "?" else None,
        "n_projects": numbers.get("n_projects"),
        "n_memory_files": memory.get("n_files"),
        "n_plans": plan_inv.get("n_plans"),
        "n_convergence_pairs": convergence.get("n_pairs"),
        "had_pr_mining": bool(pr_stats and not pr_stats.get("skipped")),
        "had_twin_spec": twin_spec_complete,
        "had_compatibility_defaults": twin_spec_compat_defaults,
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

    unfilled = set(placeholder_re.findall(profile_md + twin_md + patch_md + profile_html))
    if unfilled:
        print(f"\nNote: {len(unfilled)} placeholders still need values:")
        for k in sorted(unfilled):
            print(f"  - {{{{ {k} }}}}")
    return 0
