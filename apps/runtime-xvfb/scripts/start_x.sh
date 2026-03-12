#!/usr/bin/env bash
set -euo pipefail

DISPLAY_NUM="${DISPLAY:-:99}"
XVFB_WHD="${XVFB_WHD:-1280x1024x24}"
OPENBOX_CONFIG="${OPENBOX_CONFIG:-/opt/sandbox/openbox/rc.xml}"

Xvfb "${DISPLAY_NUM}" -screen 0 "${XVFB_WHD}" -ac +extension RANDR &
sleep 2

# Set keyboard layout to US to ensure basic compatibility
setxkbmap us || true

DISPLAY="${DISPLAY_NUM}" openbox --config-file "${OPENBOX_CONFIG}" &
wait -n
