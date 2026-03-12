#!/usr/bin/env bash
# Purpose: Delete an existing sandbox and clear the locally cached sandbox ID used by the manual smoke scripts.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/_common.sh"

require_sandbox_id

if [[ ${#auth_args[@]} -gt 0 ]]; then
  status_code="$(curl -sS -o /dev/null -w '%{http_code}' -X DELETE "${auth_args[@]}" "$BASE_URL/sandbox/$SANDBOX_ID")"
else
  status_code="$(curl -sS -o /dev/null -w '%{http_code}' -X DELETE "$BASE_URL/sandbox/$SANDBOX_ID")"
fi
if [[ "$status_code" != "204" ]]; then
  echo "Delete failed with HTTP $status_code" >&2
  exit 1
fi

echo "Deleted sandbox $SANDBOX_ID"
