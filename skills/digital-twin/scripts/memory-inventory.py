#!/usr/bin/env python3
"""
memory-inventory.py — Phase 4a of the digital-twin skill.

Walks ~/.claude/projects/*/memory/ directories. Each memory file is a markdown
file with YAML frontmatter (per the auto-memory contract):

    ---
    name: ...
    description: ...
    type: user|feedback|project|reference
    ---
    {{body}}

Outputs:
  memory-inventory.json — array of {project, path, type, name, description, body}
  rules.md              — human-readable index grouped by type and project

The body extraction is verbatim — quotes from feedback rules in particular
become the encoded-rules section of the final twin agent.
"""
from __future__ import annotations

import argparse
import json
import os
import re
from collections import Counter, defaultdict
from glob import glob
from pathlib import Path

from safe_paths import is_safe_input_file

FRONTMATTER_RE = re.compile(
    r"^---\s*\n(.*?)\n---\s*\n(.*)$", re.DOTALL | re.MULTILINE
)
KV_RE = re.compile(r"^([\w-]+)\s*:\s*(.*)$", re.MULTILINE)


def parse_memory_file(path: str) -> dict | None:
    try:
        with open(path, encoding="utf-8") as fp:
            content = fp.read()
    except OSError:
        return None

    m = FRONTMATTER_RE.match(content)
    if not m:
        return None
    fm_text, body = m.group(1), m.group(2).strip()
    fm = {}
    for kv in KV_RE.finditer(fm_text):
        fm[kv.group(1).lower()] = kv.group(2).strip().strip('"').strip("'")
    return {
        "path": path,
        "name": fm.get("name", ""),
        "description": fm.get("description", ""),
        "type": fm.get("type", "unknown"),
        "body": body,
    }


def project_slug(path: str) -> str:
    parts = Path(path).parts
    try:
        i = parts.index("projects")
        return parts[i + 1] if i + 1 < len(parts) else "unknown"
    except ValueError:
        return "unknown"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--source",
        default=os.path.expanduser("~/.claude/projects"),
    )
    ap.add_argument(
        "--out-json",
        default=os.path.expanduser(
            "~/.claude/digital-twin/analysis/memory-inventory.json"
        ),
    )
    ap.add_argument(
        "--out-md",
        default=os.path.expanduser(
            "~/.claude/digital-twin/analysis/rules.md"
        ),
    )
    args = ap.parse_args()

    source = Path(args.source).expanduser()
    out_json = Path(args.out_json).expanduser()
    out_md = Path(args.out_md).expanduser()
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_md.parent.mkdir(parents=True, exist_ok=True)

    # Find every .md inside any memory/ subdirectory.
    md_files = sorted(
        glob(str(source / "*" / "memory" / "*.md"))
        + glob(str(source / "*" / "memory" / "**" / "*.md"), recursive=True)
    )
    # Dedup while preserving order
    seen = set()
    deduped_files = []
    for path in md_files:
        if path in seen or not is_safe_input_file(path, source):
            continue
        seen.add(path)
        deduped_files.append(path)
    md_files = deduped_files

    entries: list[dict] = []
    by_type: Counter[str] = Counter()
    by_project_type: defaultdict[str, Counter[str]] = defaultdict(Counter)

    for path in md_files:
        rec = parse_memory_file(path)
        if not rec:
            continue
        # Skip MEMORY.md index files
        if Path(path).name == "MEMORY.md":
            continue
        slug = project_slug(path)
        rec["project"] = slug
        entries.append(rec)
        by_type[rec["type"]] += 1
        by_project_type[slug][rec["type"]] += 1

    with open(out_json, "w", encoding="utf-8") as fp:
        json.dump(
            {
                "n_files": len(entries),
                "by_type": dict(by_type),
                "by_project_type": {
                    k: dict(v) for k, v in by_project_type.items()
                },
                "entries": entries,
            },
            fp,
            indent=2,
            ensure_ascii=False,
        )

    # Markdown index
    md = []
    md.append("# Memory Inventory (auto-generated)\n")
    md.append(f"- **Total memory files:** {len(entries)}")
    md.append(f"- **Projects with memory:** {len(by_project_type)}")
    md.append("")
    md.append("## By type\n")
    md.append("| Type | Count |")
    md.append("| --- | ---: |")
    for t, c in by_type.most_common():
        md.append(f"| {t} | {c} |")
    md.append("")

    md.append("## Per project breakdown\n")
    md.append("| Project | user | feedback | project | reference | unknown | total |")
    md.append("| --- | ---: | ---: | ---: | ---: | ---: | ---: |")
    for slug in sorted(by_project_type, key=lambda k: -sum(by_project_type[k].values())):
        counts = by_project_type[slug]
        total = sum(counts.values())
        md.append(
            f"| {slug} | {counts.get('user', 0)} | {counts.get('feedback', 0)} "
            f"| {counts.get('project', 0)} | {counts.get('reference', 0)} "
            f"| {counts.get('unknown', 0)} | {total} |"
        )
    md.append("")

    # Render encoded feedback rules — the most important section for the twin
    feedback_entries = [e for e in entries if e["type"] == "feedback"]
    md.append(f"## Encoded feedback rules ({len(feedback_entries)} total)\n")
    md.append(
        "These rules are the most direct guide to the twin's behavior. Quote "
        "verbatim into the twin subagent's encoded-rules section.\n"
    )
    for i, e in enumerate(feedback_entries, 1):
        md.append(f"### {i}. {e.get('name') or Path(e['path']).stem}")
        md.append(f"_Project: `{e['project']}` · File: `{Path(e['path']).name}`_\n")
        if e.get("description"):
            md.append(f"**Description:** {e['description']}\n")
        md.append(e["body"])
        md.append("\n---\n")
    md.append("")

    # Render project rules (state-of-the-world, deadlines, etc.)
    project_entries = [e for e in entries if e["type"] == "project"]
    md.append(f"## Project context memories ({len(project_entries)} total)\n")
    for i, e in enumerate(project_entries, 1):
        md.append(f"### {i}. {e.get('name') or Path(e['path']).stem}")
        md.append(f"_Project: `{e['project']}`_\n")
        if e.get("description"):
            md.append(f"**Description:** {e['description']}\n")
        md.append(e["body"])
        md.append("\n---\n")
    md.append("")

    # Render user identity memories
    user_entries = [e for e in entries if e["type"] == "user"]
    md.append(f"## User identity memories ({len(user_entries)} total)\n")
    for i, e in enumerate(user_entries, 1):
        md.append(f"### {i}. {e.get('name') or Path(e['path']).stem}")
        md.append(f"_Project: `{e['project']}`_\n")
        if e.get("description"):
            md.append(f"**Description:** {e['description']}\n")
        md.append(e["body"])
        md.append("\n---\n")
    md.append("")

    # Render reference pointers
    ref_entries = [e for e in entries if e["type"] == "reference"]
    md.append(f"## External-system references ({len(ref_entries)} total)\n")
    for i, e in enumerate(ref_entries, 1):
        md.append(f"### {i}. {e.get('name') or Path(e['path']).stem}")
        md.append(f"_Project: `{e['project']}`_\n")
        if e.get("description"):
            md.append(f"**Description:** {e['description']}\n")
        md.append(e["body"])
        md.append("\n---\n")

    with open(out_md, "w", encoding="utf-8") as fp:
        fp.write("\n".join(md))

    print(f"Wrote: {out_json}")
    print(f"Wrote: {out_md}")
    print("\nQuick summary:")
    print(f"  total memory files: {len(entries)}")
    print(f"  feedback rules:     {by_type.get('feedback', 0)}")
    print(f"  project memories:   {by_type.get('project', 0)}")
    print(f"  user memories:      {by_type.get('user', 0)}")
    print(f"  reference memories: {by_type.get('reference', 0)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
