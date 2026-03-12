#!/usr/bin/env bash
set -euo pipefail

DISPLAY_NUM="${XPRA_DISPLAY:-${DISPLAY:-:100}}"
XPRA_BIND_HOST="${XPRA_BIND_HOST:-0.0.0.0}"
XPRA_PORT="${XPRA_PORT:-14500}"
XPRA_HTML5="${XPRA_HTML5:-on}"
XPRA_RUNTIME_DIR="${XPRA_RUNTIME_DIR:-/run/user/0/xpra}"
OPENBOX_RC="${OPENBOX_RC:-/opt/sandbox/openbox/rc.xml}"

mkdir -p "${XPRA_RUNTIME_DIR}" /run/user/0
rm -rf "${XPRA_RUNTIME_DIR:?}/"*
xpra stop "${DISPLAY_NUM}" >/dev/null 2>&1 || true

exec xpra start "${DISPLAY_NUM}" \
  --daemon=no \
  --bind-tcp="${XPRA_BIND_HOST}:${XPRA_PORT}" \
  --html="${XPRA_HTML5}" \
  --start-child="openbox --config-file ${OPENBOX_RC}" \
  --exit-with-children=no \
  --pulseaudio=no \
  --notifications=no \
  --systemd-run=no \
  --mdns=no \
  --printing=no \
  --file-transfer=yes \
  --dbus-launch=no
