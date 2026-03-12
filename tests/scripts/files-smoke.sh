#!/usr/bin/env bash
# Purpose: Reuse a sandbox and verify the file APIs against the shared workspace.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/_common.sh"

require_sandbox_id

run_dir="$ARTIFACTS_DIR/files-$(timestamp)"
mkdir -p "$run_dir"
content="hello verge from $(timestamp)"

api_json POST "$BASE_URL/sandbox/$SANDBOX_ID/files/write" \
  -H 'Content-Type: application/json' \
  -d "{\"path\":\"/workspace/manual-notes.txt\",\"content\":\"$content\",\"overwrite\":true}" \
  | tee "$run_dir/write.json" >/dev/null

api_json GET "$BASE_URL/sandbox/$SANDBOX_ID/files/list?path=/workspace" \
  | tee "$run_dir/list.json" >/dev/null

api_json GET "$BASE_URL/sandbox/$SANDBOX_ID/files/read?path=/workspace/manual-notes.txt" \
  | tee "$run_dir/read.json" >/dev/null

api_file GET "$BASE_URL/sandbox/$SANDBOX_ID/files/download?path=/workspace/manual-notes.txt" \
  > "$run_dir/manual-notes.txt"

echo "Artifacts saved to $run_dir"
echo "List response:   $run_dir/list.json"
echo "Read response:   $run_dir/read.json"
echo "Downloaded file: $run_dir/manual-notes.txt"
