#!/usr/bin/env bash
set -euo pipefail

curl --fail --silent http://127.0.0.1:9222/json/version >/dev/null
curl --fail --silent "http://127.0.0.1:${WEBSOCKET_PROXY_PORT:-6080}/vnc.html" >/dev/null
