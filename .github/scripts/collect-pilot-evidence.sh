#!/usr/bin/env bash
set -euo pipefail
case "${1:-}" in
  preapproval|final) stage="$1" ;;
  *) exit 2 ;;
esac
mkdir -p "$RUNNER_TEMP/pilot-evidence" "$RUNNER_TEMP/sealed-pilot/$stage"
evidence_paths=(target)
# Match Flow's resolveProductionGitHubIssueHostRoot: each checkout owns only
# the subtree keyed by the SHA-256 of its canonical project root.
project_identity="$(node -e 'const { createHash } = require("node:crypto"); const { realpathSync } = require("node:fs"); process.stdout.write(createHash("sha256").update(realpathSync(process.argv[1])).digest("hex").slice(0, 32));' "$GITHUB_WORKSPACE/target")"
collection=".flow-issue-host-$(id -u)/$project_identity"
if test -d "$GITHUB_WORKSPACE/$collection"; then
  evidence_paths+=("$collection")
fi
tar -czf "$RUNNER_TEMP/pilot-$stage.tar.gz" \
  --exclude='node_modules' --exclude='.git' \
  -C "$RUNNER_TEMP" pilot-evidence \
  -C "$GITHUB_WORKSPACE" "${evidence_paths[@]}"
node "$GITHUB_WORKSPACE/target/.github/scripts/seal-pilot-evidence.mjs" \
  "$RUNNER_TEMP/pilot-$stage.tar.gz" "$RUNNER_TEMP/sealed-pilot/$stage/evidence.aes256gcm"
