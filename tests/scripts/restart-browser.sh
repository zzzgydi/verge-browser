#!/usr/bin/env bash
# Purpose: Restart Chromium inside an existing sandbox and print sandbox info before and after the restart.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/_common.sh"

require_sandbox_id

run_dir="$ARTIFACTS_DIR/restart-$(timestamp)"
mkdir -p "$run_dir"

api_json GET "$BASE_URL/sandbox/$SANDBOX_ID" | tee "$run_dir/before.json" >/dev/null
api_json POST "$BASE_URL/sandbox/$SANDBOX_ID/browser/restart" \
  -H 'Content-Type: application/json' \
  -d '{"level":"hard"}' \
  | tee "$run_dir/restart.json" >/dev/null
api_json GET "$BASE_URL/sandbox/$SANDBOX_ID" | tee "$run_dir/after.json" >/dev/null

echo "Artifacts saved to $run_dir"
echo "Before:  $run_dir/before.json"
echo "Restart: $run_dir/restart.json"
echo "After:   $run_dir/after.json"
