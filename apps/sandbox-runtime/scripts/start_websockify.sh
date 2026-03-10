#!/usr/bin/env bash
set -euo pipefail

VNC_SERVER_PORT="${VNC_SERVER_PORT:-5900}"
WEBSOCKET_PROXY_PORT="${WEBSOCKET_PROXY_PORT:-6080}"
NOVNC_WEB_ROOT="${NOVNC_WEB_ROOT:-/usr/share/novnc}"

exec websockify --web "${NOVNC_WEB_ROOT}" "${WEBSOCKET_PROXY_PORT}" "localhost:${VNC_SERVER_PORT}"
