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

# Clean up EVERYTHING fcitx-related to prevent "already running" errors
echo "Cleaning up fcitx5 state..."
rm -rf /tmp/fcitx*
rm -rf /tmp/.fcitx*
rm -rf $HOME/.config/fcitx5/dbus/*
# Kill any lingering fcitx5 processes if they somehow exist (unlikely in fresh container but safe)
pkill -9 fcitx5 || true

# Set IM environment variables
export XMODIFIERS="@im=fcitx"
export GTK_IM_MODULE="fcitx"
export QT_IM_MODULE="fcitx"
export CLUTTER_IM_MODULE="fcitx"
export LC_ALL=zh_CN.UTF-8
export LANG=zh_CN.UTF-8
export LC_CTYPE=zh_CN.UTF-8

# Wait for DBus session bus
echo "Checking DBus session bus..."
MAX_DBUS_RETRIES=30
DBUS_COUNT=0
until dbus-send --session --dest=org.freedesktop.DBus --type=method_call --print-reply /org/freedesktop/DBus org.freedesktop.DBus.ListNames > /dev/null 2>&1 || [ $DBUS_COUNT -eq $MAX_DBUS_RETRIES ]; do
    echo "Waiting for DBus session bus... ($DBUS_COUNT/$MAX_DBUS_RETRIES)"
    sleep 1
    DBUS_COUNT=$((DBUS_COUNT + 1))
done

echo "Starting fcitx5 with verbose output..."
# Use --replace to force take over the selection if it exists
# Use --verbose to set logging level
# We use exec to let supervisor manage the process
exec fcitx5 -u pinyin --replace --verbose default=5 2>&1
