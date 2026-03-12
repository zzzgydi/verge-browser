#!/usr/bin/env bash
set -euo pipefail

# Ensure HOME and config directory are set for fcitx5
export HOME=/root
mkdir -p $HOME/.config/fcitx5
# Try to copy from either source location (due to renames in main)
if [ -f /root/.config/fcitx5/profile_src ]; then
    cp /root/.config/fcitx5/profile_src $HOME/.config/fcitx5/profile || true
elif [ -f /opt/sandbox/fcitx/profile ]; then
    cp /opt/sandbox/fcitx/profile $HOME/.config/fcitx5/profile || true
fi

DISPLAY="${DISPLAY:-:99}"

MAX_RETRIES=30
COUNT=0
until xdpyinfo -display "$DISPLAY" > /dev/null 2>&1 || [ $COUNT -eq $MAX_RETRIES ]; do
    echo "Waiting for X server on $DISPLAY... ($COUNT/$MAX_RETRIES)"
    sleep 1
    COUNT=$((COUNT + 1))
done

# Clean up old fcitx5 sockets/locks
rm -rf /tmp/fcitx*
rm -rf $HOME/.config/fcitx5/dbus/*

# Set IM environment variables
export XMODIFIERS="@im=fcitx"
export GTK_IM_MODULE="fcitx"
export QT_IM_MODULE="fcitx"
export CLUTTER_IM_MODULE="fcitx"
export LC_ALL=zh_CN.UTF-8
export LANG=zh_CN.UTF-8
export LC_CTYPE=zh_CN.UTF-8

echo "Starting fcitx5 in foreground..."
# fcitx5 -d: daemon (we don't want)
# just run fcitx5, it will stay in foreground
exec fcitx5 2>&1
