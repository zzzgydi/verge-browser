#!/usr/bin/env bash
# Purpose: Create or reuse a sandbox, mint a VNC ticket, and print a browser-ready noVNC URL for human takeover.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/_common.sh"

create_output="$("$SCRIPT_DIR/create-sandbox.sh")"
echo "$create_output"
SANDBOX_ID="$(printf '%s\n' "$create_output" | awk -F= '/^export SANDBOX_ID=/{print $2}' | tail -n1)"
VNC_TICKET_MODE="${VNC_TICKET_MODE:-one_time}"
VNC_TICKET_TTL_SEC="${VNC_TICKET_TTL_SEC:-}"

if [[ -z "${SANDBOX_ID:-}" ]]; then
  echo "Failed to resolve SANDBOX_ID." >&2
  exit 1
fi

ticket_payload="$(printf '{"mode":"%s"' "$VNC_TICKET_MODE")"
if [[ -n "$VNC_TICKET_TTL_SEC" ]]; then
  ticket_payload="$(printf '%s,"ttl_sec":%s' "$ticket_payload" "$VNC_TICKET_TTL_SEC")"
fi
ticket_payload="$(printf '%s}' "$ticket_payload")"

ticket_json="$(api_json POST "$BASE_URL/sandboxes/$SANDBOX_ID/vnc/tickets" -H 'Content-Type: application/json' -d "$ticket_payload")"
ticket="$(printf '%s' "$ticket_json" | json_get 'data["ticket"]')"
vnc_url="$BASE_URL/sandboxes/$SANDBOX_ID/vnc/?ticket=$ticket&autoconnect=true&resize=scale"

echo
echo "Open this URL in a browser:"
echo "$vnc_url"
echo "Ticket mode: $VNC_TICKET_MODE"
if [[ -n "$VNC_TICKET_TTL_SEC" ]]; then
  echo "Ticket TTL:  $VNC_TICKET_TTL_SEC seconds"
fi
