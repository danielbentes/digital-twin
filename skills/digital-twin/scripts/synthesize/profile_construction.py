"""Profile narrative and structured-card construction helpers."""
from __future__ import annotations

import re

from .shared import md_to_html_inline


def _esc(s: str) -> str:
    """HTML-escape, preserving common inline markdown."""
    return md_to_html_inline(s)


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
