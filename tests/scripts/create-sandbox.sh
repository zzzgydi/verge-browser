#!/usr/bin/env bash
# Purpose: Create a sandbox and print the IDs and URLs you need for follow-up manual tests.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/_common.sh"

WIDTH="${WIDTH:-1440}"
HEIGHT="${HEIGHT:-900}"
DEFAULT_URL="${DEFAULT_URL:-https://github.com/zzzgydi/verge-browser}"

payload=$(printf '{"width":%s,"height":%s,"default_url":"%s"}' "$WIDTH" "$HEIGHT" "$DEFAULT_URL")

response="$(api_json POST "$BASE_URL/sandboxes" -H 'Content-Type: application/json' -d "$payload")"
sandbox_id="$(printf '%s' "$response" | json_get 'data["id"]')"

printf '%s\n' "$response" | json_dump_pretty
echo
echo "Sandbox created."
echo "export SANDBOX_ID=$sandbox_id"
echo "Sandbox URL: $BASE_URL/sandboxes/$sandbox_id"
echo "CDP info:    $BASE_URL/sandboxes/$sandbox_id/browser/cdp/info"
echo "VNC ticket:  $BASE_URL/sandboxes/$sandbox_id/vnc/tickets"
