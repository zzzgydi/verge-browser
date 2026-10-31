#!/usr/bin/env bash
set -euo pipefail

if [ "${BROWSER_ENGINE:-chromium}" = "camoufox" ]; then
  printf '%s\n' '{"action":"status"}' | /opt/sandbox/camoufox-venv/bin/python /opt/sandbox/camoufox/camoufox_control.py >/dev/null
else
  curl --fail --silent http://127.0.0.1:9222/json/version >/dev/null
fi
curl --fail --silent "http://127.0.0.1:${WEBSOCKET_PROXY_PORT:-6080}/vnc.html" >/dev/null
