#!/usr/bin/env bash
set -euo pipefail

# Generate machine-id if it doesn't exist (critical for DBus in Docker)
mkdir -p /var/lib/dbus
dbus-uuidgen --ensure

# Start DBus session bus and export address
# dbus-launch --sh-syntax output is designed to be eval'd
eval $(dbus-launch --sh-syntax)
export DBUS_SESSION_BUS_ADDRESS

echo "DBUS_SESSION_BUS_ADDRESS is $DBUS_SESSION_BUS_ADDRESS"

exec /usr/bin/supervisord -n -c /etc/supervisor/conf.d/supervisord.conf
