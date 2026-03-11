#!/usr/bin/env bash
set -euo pipefail

# Ensure HOME is set
export HOME=/root
mkdir -p $HOME/.config/fcitx

# Wait for X server to be ready
MAX_RETRIES=30
COUNT=0
until xdpyinfo -display "$DISPLAY" > /dev/null 2>&1 || [ $COUNT -eq $MAX_RETRIES ]; do
    echo "Waiting for X server on $DISPLAY... ($COUNT/$MAX_RETRIES)"
    sleep 1
    COUNT=$((COUNT + 1))
done

# Clean up old fcitx sockets/locks
rm -rf /tmp/fcitx*
rm -rf $HOME/.config/fcitx/dbus/*

# Set IM environment variables
export XMODIFIERS="@im=fcitx"
export GTK_IM_MODULE="fcitx"
export QT_IM_MODULE="fcitx"
export LC_ALL=zh_CN.UTF-8
export LANG=zh_CN.UTF-8

# Use dbus-run-session to ensure fcitx has a valid dbus connection
# -D: do not run as daemon
exec dbus-run-session -- fcitx -D 2>&1
