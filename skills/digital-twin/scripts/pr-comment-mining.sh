#!/usr/bin/env bash
# pr-comment-mining.sh — Phase 4d of the digital-twin skill.
#
# Mines the user's recent PR comments using the GitHub CLI. Optional: if `gh`
# is not installed or not authenticated, the script exits cleanly with a
# message and the rest of the pipeline still works.
#
# Strategy:
#   1. Find the user's 10 most recent PRs as author (across all repos they
#      can see).
#   2. For each PR, fetch issue comments + review comments authored by the
#      user.
#   3. Detect structural patterns:
#        * H2 header presence (`^## `)
#        * P1/P2/P3 finding-table presence (`| P[123] |` row markers)
#        * HTML state markers (`<!-- FLOW_RESOLUTION_CYCLE`, etc.)
#        * Inline-vs-overview ratio
#   4. Emit pr-comments.json + pr-template.md
#
# Outputs land in ~/.claude/digital-twin/analysis/ by default.

set -euo pipefail

OUT_DIR="$HOME/.claude/digital-twin/analysis"
OUT_JSON=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --out-dir)
      OUT_DIR="${2:?missing value for --out-dir}"
      shift 2
      ;;
    --out|--out-json)
      OUT_JSON="${2:?missing value for $1}"
      if [[ "$OUT_JSON" == */* ]]; then
        OUT_DIR="${OUT_JSON%/*}"
      else
        OUT_DIR="."
      fi
      shift 2
      ;;
    -*)
      echo "Unknown option: $1" >&2
      exit 2
      ;;
    *)
      OUT_DIR="$1"
      shift
      ;;
  esac
done

mkdir -p -- "$OUT_DIR"

OUT_JSON="${OUT_JSON:-$OUT_DIR/pr-comments.json}"
OUT_MD="$OUT_DIR/pr-template.md"
TMP_DIR="$(mktemp -d -t digital-twin-pr.XXXXXX)"
trap 'rm -rf "$TMP_DIR"' EXIT

# ---- guards --------------------------------------------------------------

if ! command -v gh >/dev/null 2>&1; then
  echo "gh CLI not installed — skipping PR comment mining."
  echo "{\"skipped\": true, \"reason\": \"gh CLI not installed\"}" > "$OUT_JSON"
  echo "# PR comment mining — skipped (gh CLI not installed)" > "$OUT_MD"
  exit 0
fi

if ! gh auth status >/dev/null 2>&1; then
  echo "gh CLI not authenticated — skipping PR comment mining."
  echo "Run: gh auth login   then re-run /digital-twin update"
  echo "{\"skipped\": true, \"reason\": \"gh CLI not authenticated\"}" > "$OUT_JSON"
  echo "# PR comment mining — skipped (gh CLI not authenticated)" > "$OUT_MD"
  exit 0
fi

USER_LOGIN="$(gh api user --jq '.login' 2>/dev/null || echo "")"
if [[ -z "$USER_LOGIN" ]]; then
  echo "Could not resolve GitHub login — skipping PR mining."
  echo "{\"skipped\": true, \"reason\": \"cannot resolve gh user\"}" > "$OUT_JSON"
  echo "# PR comment mining — skipped (cannot resolve gh user)" > "$OUT_MD"
  exit 0
fi

echo "GitHub user: $USER_LOGIN"

# ---- find user's recent PRs ---------------------------------------------

PRS_JSON="$TMP_DIR/prs.json"
gh search prs \
  --author "@me" \
  --limit 20 \
  --json url,title,repository,number,state,createdAt \
  > "$PRS_JSON" 2>/dev/null || echo "[]" > "$PRS_JSON"

PR_COUNT="$(python3 - "$PRS_JSON" <<'PYEOF'
import json
import sys
with open(sys.argv[1], encoding="utf-8") as fp:
    print(len(json.load(fp)))
PYEOF
)"
echo "Found $PR_COUNT recent PRs"

if [[ "$PR_COUNT" -eq 0 ]]; then
  echo "{\"skipped\": false, \"n_prs\": 0, \"n_comments\": 0}" > "$OUT_JSON"
  echo "# PR comment mining — no recent PRs found" > "$OUT_MD"
  exit 0
fi

# ---- collect comments per PR --------------------------------------------

COMMENTS_JSONL="$TMP_DIR/comments.jsonl"
: > "$COMMENTS_JSONL"

python3 - "$PRS_JSON" "$USER_LOGIN" "$COMMENTS_JSONL" <<'PYEOF'
import json
import re
import subprocess
import sys

prs_path, user, out_path = sys.argv[1], sys.argv[2], sys.argv[3]
with open(prs_path, encoding="utf-8") as fp:
    prs = json.load(fp)

repo_re = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")

with open(out_path, "w", encoding="utf-8") as out:
    for pr in prs:
        repo_obj = pr.get("repository", {})
        # gh search prs returns repository as {name, nameWithOwner, ...}
        full_name = repo_obj.get("nameWithOwner") or repo_obj.get("name") or ""
        if not full_name:
            continue
        if not repo_re.match(full_name):
            print(f"Skipping PR with unexpected repo name: {full_name}", file=sys.stderr)
            continue
        number = pr.get("number")
        if not number:
            continue
        try:
            number = int(number)
        except (TypeError, ValueError):
            print(f"Skipping PR with unexpected number: {number}", file=sys.stderr)
            continue
        for endpoint in ("issues", "pulls"):
            api_path = f"repos/{full_name}/{endpoint}/{number}/comments"
            try:
                raw = subprocess.check_output(
                    ["gh", "api", api_path, "--paginate"],
                    stderr=subprocess.DEVNULL,
                )
            except subprocess.CalledProcessError:
                continue
            try:
                comments = json.loads(raw or "[]")
            except json.JSONDecodeError:
                continue
            if not isinstance(comments, list):
                continue
            for c in comments:
                login = (c.get("user") or {}).get("login")
                if login != user:
                    continue
                body = c.get("body") or ""
                if not body.strip():
                    continue
                out.write(json.dumps({
                    "repo": full_name,
                    "pr": number,
                    "endpoint": endpoint,
                    "url": c.get("html_url"),
                    "created_at": c.get("created_at"),
                    "body": body,
                }) + "\n")
PYEOF

COMMENT_COUNT="$(wc -l < "$COMMENTS_JSONL" | tr -d ' ')"
echo "Collected $COMMENT_COUNT user-authored PR comments"

if [[ "$COMMENT_COUNT" -eq 0 ]]; then
  echo "{\"skipped\": false, \"n_prs\": $PR_COUNT, \"n_comments\": 0}" > "$OUT_JSON"
  echo "# PR comment mining — no user-authored comments found on recent PRs" > "$OUT_MD"
  exit 0
fi

# ---- analyze structural patterns ----------------------------------------

python3 - "$COMMENTS_JSONL" "$OUT_JSON" "$OUT_MD" <<'PYEOF'
import json
import re
import statistics
import sys

comments_path, out_json, out_md = sys.argv[1], sys.argv[2], sys.argv[3]

H2_RE = re.compile(r"^##\s+\S", re.MULTILINE)
PRIORITY_TABLE_RE = re.compile(r"\|\s*P[123]\s*\|", re.IGNORECASE)
HTML_MARKER_RE = re.compile(r"<!--\s*\w+", re.MULTILINE)
FINDING_ROW_RE = re.compile(
    r"^\|\s*(?:P[123]|\w+)\s*\|.*\|.*\|", re.MULTILINE
)
CHECKLIST_RE = re.compile(r"^\s*-\s*\[\s?[xX]?\s?\]", re.MULTILINE)

records = []
with open(comments_path, encoding="utf-8") as fp:
    for line in fp:
        line = line.strip()
        if not line:
            continue
        records.append(json.loads(line))

n = len(records)
lengths = [len(r["body"]) for r in records]
h2_count = sum(1 for r in records if H2_RE.search(r["body"]))
priority_count = sum(1 for r in records if PRIORITY_TABLE_RE.search(r["body"]))
html_marker_count = sum(1 for r in records if HTML_MARKER_RE.search(r["body"]))
checklist_count = sum(1 for r in records if CHECKLIST_RE.search(r["body"]))

stats = {
    "n_comments": n,
    "n_prs_with_comments": len({(r["repo"], r["pr"]) for r in records}),
    "median_length_chars": int(statistics.median(lengths)) if lengths else 0,
    "p90_length_chars": (
        int(statistics.quantiles(lengths, n=10)[-1])
        if len(lengths) >= 10
        else (max(lengths) if lengths else 0)
    ),
    "h2_share_pct": round(100 * h2_count / n, 1) if n else 0,
    "priority_table_share_pct": round(100 * priority_count / n, 1) if n else 0,
    "html_marker_share_pct": round(100 * html_marker_count / n, 1) if n else 0,
    "checklist_share_pct": round(100 * checklist_count / n, 1) if n else 0,
    "longest_examples": [
        {"repo": r["repo"], "pr": r["pr"], "url": r["url"], "preview": r["body"][:500]}
        for r in sorted(records, key=lambda x: -len(x["body"]))[:5]
    ],
}

with open(out_json, "w", encoding="utf-8") as fp:
    json.dump(stats, fp, indent=2)

md = []
md.append("# PR Comment Style (auto-generated)\n")
md.append(f"- **Comments analyzed:** {n:,} across {stats['n_prs_with_comments']} PRs")
md.append(f"- **Median length:** {stats['median_length_chars']:,} chars")
md.append(f"- **P90 length:** {stats['p90_length_chars']:,} chars")
md.append(f"- **Comments using H2 headers:** {stats['h2_share_pct']}%")
md.append(f"- **Comments using P1/P2/P3 tables:** {stats['priority_table_share_pct']}%")
md.append(f"- **Comments using HTML state markers:** {stats['html_marker_share_pct']}%")
md.append(f"- **Comments using checklists:** {stats['checklist_share_pct']}%")
md.append("")
md.append("## Longest PR comments (representative samples)\n")
for ex in stats["longest_examples"]:
    md.append(f"### {ex['repo']}#{ex['pr']}")
    md.append(f"_<{ex['url']}>_\n")
    md.append("```")
    md.append(ex["preview"])
    md.append("```")
    md.append("")

with open(out_md, "w", encoding="utf-8") as fp:
    fp.write("\n".join(md))

print(f"Wrote: {out_json}")
print(f"Wrote: {out_md}")
print()
print(f"Quick summary:")
print(f"  comments:    {n}")
print(f"  median len:  {stats['median_length_chars']} chars")
print(f"  uses H2:     {stats['h2_share_pct']}%")
print(f"  uses P1/P2/P3 table: {stats['priority_table_share_pct']}%")
PYEOF
