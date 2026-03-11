#!/usr/bin/env bash
# Usage: ./debug-fcitx.sh <container_id_or_name>

CONTAINER=$1
if [ -z "$CONTAINER" ]; then
    echo "Usage: $0 <container_id>"
    exit 1
fi

echo "=== 1. Checking Processes ==="
docker exec "$CONTAINER" ps aux | grep -E "fcitx|dbus|chromium"

echo -e "\n=== 2. Checking Environment Variables ==="
docker exec "$CONTAINER" env | grep -E "IM_MODULE|XMODIFIERS|LANG|LC_ALL|DBUS"

echo -e "\n=== 3. Checking DBus Session ==="
docker exec "$CONTAINER" dbus-send --session --dest=org.freedesktop.DBus --type=method_call --print-reply /org/freedesktop/DBus org.freedesktop.DBus.ListNames || echo "DBus connection failed"

echo -e "\n=== 4. Checking Fcitx Engines (Crucial) ==="
docker exec "$CONTAINER" fcitx-remote -l

echo -e "\n=== 5. Checking Fcitx Remote Status ==="
docker exec "$CONTAINER" fcitx-remote

echo -e "\n=== 6. Checking X11 IM Properties ==="
docker exec "$CONTAINER" xprop -root | grep -i "input_method"

echo -e "\n=== 7. Checking Fcitx Logs ==="
docker exec "$CONTAINER" tail -n 20 /var/log/sandbox/fcitx.err.log
