#!/usr/bin/env bash
set -euo pipefail
case "${1:-}" in
  preapproval|final) stage="$1" ;;
  *) exit 2 ;;
esac
mkdir -p "$RUNNER_TEMP/pilot-evidence" "$RUNNER_TEMP/sealed-pilot/$stage"
evidence_paths=(target)
collection=".flow-issue-host-$(id -u)"
if test -d "$GITHUB_WORKSPACE/$collection"; then
  evidence_paths+=("$collection")
fi
tar -czf "$RUNNER_TEMP/pilot-$stage.tar.gz" \
  --exclude='node_modules' --exclude='.git' \
  -C "$RUNNER_TEMP" pilot-evidence \
  -C "$GITHUB_WORKSPACE" "${evidence_paths[@]}"
node "$GITHUB_WORKSPACE/target/.github/scripts/seal-pilot-evidence.mjs" \
  "$RUNNER_TEMP/pilot-$stage.tar.gz" "$RUNNER_TEMP/sealed-pilot/$stage/evidence.aes256gcm"
