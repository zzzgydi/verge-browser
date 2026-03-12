#!/usr/bin/env bash
# Purpose: Create or reuse a sandbox, mint a session ticket, and print a browser-ready Xpra session URL for human takeover.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/_common.sh"

create_output="$("$SCRIPT_DIR/create-sandbox.sh")"
echo "$create_output"
SANDBOX_ID="$(printf '%s\n' "$create_output" | awk -F= '/^export SANDBOX_ID=/{print $2}' | tail -n1)"
SESSION_TICKET_MODE="${SESSION_TICKET_MODE:-one_time}"
SESSION_TICKET_TTL_SEC="${SESSION_TICKET_TTL_SEC:-}"

if [[ -z "${SANDBOX_ID:-}" ]]; then
  echo "Failed to resolve SANDBOX_ID." >&2
  exit 1
fi

ticket_payload="$(printf '{"mode":"%s"' "$SESSION_TICKET_MODE")"
if [[ -n "$SESSION_TICKET_TTL_SEC" ]]; then
  ticket_payload="$(printf '%s,"ttl_sec":%s' "$ticket_payload" "$SESSION_TICKET_TTL_SEC")"
fi
ticket_payload="$(printf '%s}' "$ticket_payload")"

ticket_json="$(api_json POST "$BASE_URL/sandbox/$SANDBOX_ID/session/apply" -H 'Content-Type: application/json' -d "$ticket_payload")"
session_url="$(printf '%s' "$ticket_json" | json_get 'data["session_url"]')"

echo
echo "Open this URL in a browser:"
echo "$session_url"
echo "Ticket mode: $SESSION_TICKET_MODE"
if [[ -n "$SESSION_TICKET_TTL_SEC" ]]; then
  echo "Ticket TTL:  $SESSION_TICKET_TTL_SEC seconds"
fi
