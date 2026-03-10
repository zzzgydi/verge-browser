#!/usr/bin/env bash
set -euo pipefail

DISPLAY_NUM="${DISPLAY:-:99}"
BROWSER_WINDOW_WIDTH="${BROWSER_WINDOW_WIDTH:-1280}"
BROWSER_WINDOW_HEIGHT="${BROWSER_WINDOW_HEIGHT:-1024}"
BROWSER_USER_DATA_DIR="${BROWSER_USER_DATA_DIR:-/workspace/browser-profile}"
BROWSER_DOWNLOAD_DIR="${BROWSER_DOWNLOAD_DIR:-/workspace/downloads}"
DEFAULT_URL="${DEFAULT_URL:-about:blank}"

mkdir -p "${BROWSER_USER_DATA_DIR}" "${BROWSER_DOWNLOAD_DIR}" /tmp/chrome-cache
rm -f "${BROWSER_USER_DATA_DIR}"/Singleton{Cookie,Lock,Socket} || true

exec chromium \
  --display="${DISPLAY_NUM}" \
  --no-sandbox \
  --no-first-run \
  --no-default-browser-check \
  --disable-background-networking \
  --disable-dev-shm-usage \
  --disable-gpu \
  --disable-popup-blocking \
  --disable-features=TranslateUI \
  --window-size="${BROWSER_WINDOW_WIDTH},${BROWSER_WINDOW_HEIGHT}" \
  --user-data-dir="${BROWSER_USER_DATA_DIR}" \
  --remote-debugging-address=0.0.0.0 \
  --remote-debugging-port=9222 \
  --disk-cache-dir=/tmp/chrome-cache \
  --force-color-profile=srgb \
  --lang=en-US \
  "${DEFAULT_URL}"
