#!/usr/bin/env bash
set -euo pipefail

DISPLAY_NUM="${DISPLAY:-:99}"
VNC_SERVER_PORT="${VNC_SERVER_PORT:-5900}"

exec x11vnc \
  -display "${DISPLAY_NUM}" \
  -forever \
  -shared \
  -rfbport "${VNC_SERVER_PORT}" \
  -nopw \
  -localhost \
  -xkb \
  -noxdamage \
  -nowf
