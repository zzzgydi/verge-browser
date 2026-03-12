#!/usr/bin/env bash
# Purpose: Shared helpers for manual Verge Browser API smoke scripts.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ARTIFACTS_DIR="$SCRIPT_DIR/.artifacts"

mkdir -p "$ARTIFACTS_DIR"

BASE_URL="${VERGE_BROWSER_URL:-http://127.0.0.1:8000}"
VERGE_BROWSER_TOKEN="${VERGE_BROWSER_TOKEN:-}"

auth_args=()
if [[ -n "$VERGE_BROWSER_TOKEN" ]]; then
  auth_args=(-H "Authorization: Bearer $VERGE_BROWSER_TOKEN")
fi

require_auth_token() {
  if [[ -n "$VERGE_BROWSER_TOKEN" ]]; then
    return 0
  fi
  cat >&2 <<'EOF'
Missing admin bearer token.

Set this environment variable before running the manual API scripts:
  export VERGE_BROWSER_TOKEN="<admin-token>"

The value must match the API server's VERGE_ADMIN_AUTH_TOKEN.
EOF
  exit 1
}

json_get() {
  local expr="$1"
  python3 -c 'import json,sys; data=json.load(sys.stdin); print(eval(sys.argv[1], {"__builtins__": {}}, {"data": data}))' "$expr"
}

json_dump_pretty() {
  python3 -m json.tool
}

api_json() {
  local method="$1"
  local url="$2"
  shift 2
  require_auth_token
  if [[ ${#auth_args[@]} -gt 0 ]]; then
    curl -fsS -X "$method" "${auth_args[@]}" "$url" "$@"
  else
    curl -fsS -X "$method" "$url" "$@"
  fi
}

api_file() {
  local method="$1"
  local url="$2"
  shift 2
  require_auth_token
  if [[ ${#auth_args[@]} -gt 0 ]]; then
    curl -fsS -X "$method" "${auth_args[@]}" "$url" "$@"
  else
    curl -fsS -X "$method" "$url" "$@"
  fi
}

require_sandbox_id() {
  if [[ -z "${SANDBOX_ID:-}" ]]; then
    echo "SANDBOX_ID is required. Pass it explicitly, for example:" >&2
    echo "SANDBOX_ID=sb_xxx tests/scripts/browser-smoke.sh" >&2
    exit 1
  fi
}

timestamp() {
  date +"%Y%m%d-%H%M%S"
}
