#!/usr/bin/env python3
"""
plan-inventory.py — Phase 4b of the digital-twin skill.

Surveys plan-like documents across the user's projects and home directory:
  * ~/.claude/plans/*.md
  * <each-project>/.decisions/*.md
  * <each-project>/docs/plans/*.md
  * <each-project>/plans/*.md

For each, detects:
  * archetype: 'surgical' (single-PR, short) vs 'multi-phase' (multi-section, has Phase headings)
  * presence of YAML frontmatter
  * presence of an "Out of scope" / "Non-goals" section
  * acceptance-criteria count (lines starting with "- [ ]" or numbered AC items)
  * verification-evidence section presence
  * file mtime (for drift over time analysis)

Outputs:
  plan-inventory.json — array of {path, archetype, frontmatter, has_oos, ac_count, has_verification, mtime}
  plans.md           — human-readable index sorted by mtime
"""
from __future__ import annotations

import argparse
import json
import os
import re
from datetime import datetime
from glob import glob
from pathlib import Path

FRONTMATTER_RE = re.compile(r"^---\s*\n.*?\n---\s*\n", re.DOTALL)
PHASE_RE = re.compile(r"^##+\s+(?:Phase|Step|Stage)\b", re.MULTILINE | re.IGNORECASE)
OOS_RE = re.compile(
    r"^##+\s+(?:out[\s-]?of[\s-]?scope|non[\s-]?goals?|will not)\b",
    re.MULTILINE | re.IGNORECASE,
)
VERIFICATION_RE = re.compile(
    r"^##+\s+(?:verification|verification evidence|acceptance|how we know)\b",
    re.MULTILINE | re.IGNORECASE,
)
AC_LINE_RE = re.compile(r"^\s*(?:[-*]\s*\[\s?\]|\d+\.)\s+", re.MULTILINE)


def classify(text: str) -> str:
    phases = len(PHASE_RE.findall(text))
    if phases >= 2:
        return "multi-phase"
    if len(text) > 6000:
        return "multi-phase"
    return "surgical"


def inventory_file(path: str) -> dict:
    try:
        with open(path, encoding="utf-8", errors="replace") as fp:
            text = fp.read()
    except OSError:
        return {}
    mtime = datetime.fromtimestamp(os.path.getmtime(path)).isoformat()
    return {
        "path": path,
        "size_bytes": os.path.getsize(path),
        "mtime": mtime,
        "archetype": classify(text),
        "has_frontmatter": bool(FRONTMATTER_RE.match(text)),
        "has_oos": bool(OOS_RE.search(text)),
        "has_verification": bool(VERIFICATION_RE.search(text)),
        "ac_count": len(AC_LINE_RE.findall(text)),
        "phase_count": len(PHASE_RE.findall(text)),
    }


def discover_paths(
    home: Path, projects_root: Path, search_dirs: list[Path] | None = None
) -> list[str]:
    """
    Discover plan-like markdown files in bounded locations:
      1. ~/.claude/plans/*.md
      2. <projects_root>/*/.decisions/*.md (these are inside ~/.claude/projects/)
      3. Each path in `search_dirs` (each searched up to 3 levels deep)

    We do NOT recursively glob ~ — that scans the entire home directory and is
    minutes-slow. Users with decision journals outside the default locations
    can pass --search-dir explicitly.
    """
    candidates: list[str] = []
    # User-global plans
    candidates += glob(str(home / ".claude" / "plans" / "*.md"))
    # Per-project (under ~/.claude/projects/) memory + decisions
    for proj in projects_root.iterdir() if projects_root.exists() else []:
        if not proj.is_dir():
            continue
        for pat in (".decisions/*.md", "docs/plans/*.md", "plans/*.md"):
            candidates += glob(str(proj / pat))

    # Bounded search in user-specified directories, depth 3
    for sd in search_dirs or []:
        if not sd.exists():
            continue
        for depth_pat in (
            ".decisions/*.md",
            "*/.decisions/*.md",
            "*/*/.decisions/*.md",
        ):
            candidates += glob(str(sd / depth_pat))

    # Dedup, preserve order
    seen: set[str] = set()
    out: list[str] = []
    for c in candidates:
        if c not in seen:
            seen.add(c)
            out.append(c)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--home", default=os.path.expanduser("~"),
    )
    ap.add_argument(
        "--projects",
        default=os.path.expanduser("~/.claude/projects"),
    )
    ap.add_argument(
        "--out-json",
        default=os.path.expanduser(
            "~/.claude/digital-twin/analysis/plan-inventory.json"
        ),
    )
    ap.add_argument(
        "--out-md",
        default=os.path.expanduser(
            "~/.claude/digital-twin/analysis/plans.md"
        ),
    )
    ap.add_argument(
        "--search-dir",
        action="append",
        default=[],
        help=(
            "Additional directory to scan for .decisions/*.md (depth 3). "
            "Repeat for multiple. Example: --search-dir ~/code "
            "--search-dir ~/Documents/projects"
        ),
    )
    args = ap.parse_args()

    home = Path(args.home).expanduser()
    projects = Path(args.projects).expanduser()
    out_json = Path(args.out_json).expanduser()
    out_md = Path(args.out_md).expanduser()
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_md.parent.mkdir(parents=True, exist_ok=True)

    search_dirs = [Path(p).expanduser() for p in args.search_dir]
    paths = discover_paths(home, projects, search_dirs)
    inventory = []
    for p in paths:
        info = inventory_file(p)
        if info:
            inventory.append(info)
    inventory.sort(key=lambda r: r["mtime"], reverse=True)

    # Aggregates
    n = len(inventory)
    archetypes = {"surgical": 0, "multi-phase": 0}
    has_oos = 0
    has_verification = 0
    ac_counts: list[int] = []
    for r in inventory:
        archetypes[r["archetype"]] = archetypes.get(r["archetype"], 0) + 1
        if r["has_oos"]:
            has_oos += 1
        if r["has_verification"]:
            has_verification += 1
        ac_counts.append(r["ac_count"])

    # Drift signal: out-of-scope adoption in early half vs late half of plans
    drift = None
    if n >= 4:
        half = n // 2
        early = inventory[half:]  # older (lower mtime in sorted desc)
        late = inventory[:half]   # newer
        early_oos_pct = round(100 * sum(r["has_oos"] for r in early) / len(early), 1)
        late_oos_pct = round(100 * sum(r["has_oos"] for r in late) / len(late), 1)
        early_ac_avg = (
            round(sum(r["ac_count"] for r in early) / len(early), 2) if early else 0
        )
        late_ac_avg = (
            round(sum(r["ac_count"] for r in late) / len(late), 2) if late else 0
        )
        drift = {
            "early_oos_pct": early_oos_pct,
            "late_oos_pct": late_oos_pct,
            "early_ac_avg": early_ac_avg,
            "late_ac_avg": late_ac_avg,
            "early_n": len(early),
            "late_n": len(late),
        }

    summary = {
        "n_plans": n,
        "archetypes": archetypes,
        "has_oos_count": has_oos,
        "has_oos_pct": round(100 * has_oos / n, 1) if n else 0,
        "has_verification_count": has_verification,
        "avg_ac_count": (
            round(sum(ac_counts) / len(ac_counts), 2) if ac_counts else 0
        ),
        "drift": drift,
        "plans": inventory,
    }

    with open(out_json, "w", encoding="utf-8") as fp:
        json.dump(summary, fp, indent=2, ensure_ascii=False)

    md = []
    md.append("# Plan Inventory (auto-generated)\n")
    md.append(f"- **Total plan-like documents:** {n}")
    md.append(f"- **Surgical:** {archetypes.get('surgical', 0)}")
    md.append(f"- **Multi-phase:** {archetypes.get('multi-phase', 0)}")
    md.append(f"- **With Out-of-Scope section:** {has_oos} ({summary['has_oos_pct']}%)")
    md.append(f"- **With Verification section:** {has_verification}")
    md.append(f"- **Average acceptance criteria per plan:** {summary['avg_ac_count']}")
    md.append("")
    if drift:
        md.append("## Drift signal: Out-of-Scope adoption over time\n")
        md.append(
            f"- Early half ({drift['early_n']} plans): {drift['early_oos_pct']}% have OOS · avg AC {drift['early_ac_avg']}"
        )
        md.append(
            f"- Late half ({drift['late_n']} plans): {drift['late_oos_pct']}% have OOS · avg AC {drift['late_ac_avg']}"
        )
        md.append("")

    md.append("## All plans (newest first)\n")
    md.append("| mtime | Archetype | OOS | Verif | AC | Path |")
    md.append("| --- | --- | :-: | :-: | ---: | --- |")
    for r in inventory:
        md.append(
            f"| {r['mtime'][:10]} | {r['archetype']} | "
            f"{'Y' if r['has_oos'] else '-'} | "
            f"{'Y' if r['has_verification'] else '-'} | "
            f"{r['ac_count']} | `{r['path']}` |"
        )

    with open(out_md, "w", encoding="utf-8") as fp:
        fp.write("\n".join(md))

    print(f"Wrote: {out_json}")
    print(f"Wrote: {out_md}")
    print("\nQuick summary:")
    print(f"  plans found:    {n}")
    print(f"  surgical:       {archetypes.get('surgical', 0)}")
    print(f"  multi-phase:    {archetypes.get('multi-phase', 0)}")
    print(f"  with OOS:       {has_oos} ({summary['has_oos_pct']}%)")
    if drift:
        print(
            f"  drift early→late: OOS {drift['early_oos_pct']}%→{drift['late_oos_pct']}%, "
            f"AC {drift['early_ac_avg']}→{drift['late_ac_avg']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
