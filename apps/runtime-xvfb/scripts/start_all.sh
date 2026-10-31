#!/usr/bin/env bash
set -euo pipefail

case "${BROWSER_ENGINE:-chromium}" in
  chromium)
    export BROWSER_AUTORESTART=true BROWSER_STARTRETRIES=3 BROWSER_STOPASGROUP=false BROWSER_STARTSECS=1
    ;;
  camoufox)
    export BROWSER_AUTORESTART=false BROWSER_STARTRETRIES=0 BROWSER_STOPASGROUP=true BROWSER_STARTSECS=1
    ;;
  cloakbrowser)
    export BROWSER_AUTORESTART=false BROWSER_STARTRETRIES=0 BROWSER_STOPASGROUP=true BROWSER_STARTSECS=0
    /opt/sandbox/cloak-venv/bin/python /opt/sandbox/cloak/cloak_runtime.py prepare
    ;;
  *)
    echo "Unsupported BROWSER_ENGINE; expected chromium, cloakbrowser or camoufox" >&2
    exit 1
    ;;
esac

# Generate machine-id if it doesn't exist (critical for DBus in Docker)
mkdir -p /var/lib/dbus
dbus-uuidgen --ensure

# Start DBus session bus and export address
# dbus-launch --sh-syntax output is designed to be eval'd
eval $(dbus-launch --sh-syntax)
export DBUS_SESSION_BUS_ADDRESS

echo "DBUS_SESSION_BUS_ADDRESS is $DBUS_SESSION_BUS_ADDRESS"

exec /usr/bin/supervisord -n -c /etc/supervisor/conf.d/supervisord.conf
