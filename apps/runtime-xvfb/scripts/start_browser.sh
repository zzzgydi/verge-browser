#!/usr/bin/env bash
set -euo pipefail

DISPLAY_NUM="${DISPLAY:-:99}"
BROWSER_WINDOW_WIDTH="${BROWSER_WINDOW_WIDTH:-1280}"
BROWSER_WINDOW_HEIGHT="${BROWSER_WINDOW_HEIGHT:-1024}"
BROWSER_USER_DATA_DIR="${BROWSER_USER_DATA_DIR:-/workspace/browser-profile}"
BROWSER_DOWNLOAD_DIR="${BROWSER_DOWNLOAD_DIR:-/workspace/downloads}"
DEFAULT_URL="${DEFAULT_URL:-https://github.com/zzzgydi/verge-browser}"

mkdir -p "${BROWSER_USER_DATA_DIR}" "${BROWSER_DOWNLOAD_DIR}" /tmp/chrome-cache
rm -f "${BROWSER_USER_DATA_DIR}"/Singleton{Cookie,Lock,Socket} || true

# Set IM environment variables
export XMODIFIERS="@im=fcitx"
export GTK_IM_MODULE="fcitx"
export QT_IM_MODULE="fcitx"
export CLUTTER_IM_MODULE="fcitx"
export LC_ALL=zh_CN.UTF-8
export LANG=zh_CN.UTF-8
export LC_CTYPE=zh_CN.UTF-8

# Wait for fcitx5 to be ready
echo "Waiting for fcitx5 to be ready..."
MAX_FCITX_RETRIES=30
FCITX_COUNT=0
until fcitx5-remote > /dev/null 2>&1 || [ $FCITX_COUNT -eq $MAX_FCITX_RETRIES ]; do
    sleep 1
    FCITX_COUNT=$((FCITX_COUNT + 1))
done

# Force activate input method in background loop after browser starts
(
  # Wait a bit for browser to actually open its first window
  sleep 5
  for i in {1..5}; do
    echo "Attempting to activate input method ($i/5)..."
    fcitx5-remote -o || true
    sleep 2
  done
) &

exec chromium \
  --lang=zh-CN \
  --gtk-version=3 \
  --enable-features=UseOzonePlatform \
  --ozone-platform=x11 \
  --enable-input-method-proxy \
  --display="${DISPLAY_NUM}" \
  --no-sandbox \
  --no-first-run \
  --no-default-browser-check \
  --disable-background-networking \
  --disable-dev-shm-usage \
  --disable-gpu \
  --disable-popup-blocking \
  --disable-features=TranslateUI \
  --window-position=0,0 \
  --window-size="${BROWSER_WINDOW_WIDTH},${BROWSER_WINDOW_HEIGHT}" \
  --start-maximized \
  --user-data-dir="${BROWSER_USER_DATA_DIR}" \
  --remote-debugging-address=0.0.0.0 \
  --remote-debugging-port=9222 \
  --disk-cache-dir=/tmp/chrome-cache \
  --force-color-profile=srgb \
  "${DEFAULT_URL}"
