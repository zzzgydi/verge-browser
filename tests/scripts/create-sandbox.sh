#!/usr/bin/env bash
# Purpose: Create a sandbox and print the IDs and URLs you need for follow-up manual tests.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/_common.sh"

WIDTH="${WIDTH:-1440}"
HEIGHT="${HEIGHT:-900}"
SANDBOX_KIND="${SANDBOX_KIND:-xvfb_vnc}"
DEFAULT_URL="${DEFAULT_URL:-https://github.com/zzzgydi/verge-browser}"

payload=$(printf '{"kind":"%s","width":%s,"height":%s,"default_url":"%s"}' "$SANDBOX_KIND" "$WIDTH" "$HEIGHT" "$DEFAULT_URL")

response="$(api_json POST "$BASE_URL/sandbox" -H 'Content-Type: application/json' -d "$payload")"
sandbox_id="$(printf '%s' "$response" | json_get 'data["id"]')"

printf '%s\n' "$response" | json_dump_pretty
echo
echo "Sandbox created."
echo "export SANDBOX_ID=$sandbox_id"
echo "Sandbox kind: $SANDBOX_KIND"
echo "Sandbox URL: $BASE_URL/sandbox/$sandbox_id"
echo "CDP apply:   $BASE_URL/sandbox/$sandbox_id/cdp/apply"
echo "Session apply: $BASE_URL/sandbox/$sandbox_id/session/apply"
echo "Session example: SANDBOX_KIND=$SANDBOX_KIND SESSION_TICKET_MODE=reusable SESSION_TICKET_TTL_SEC=300 $SCRIPT_DIR/get-session-url.sh"
