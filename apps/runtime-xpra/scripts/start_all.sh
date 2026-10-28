#!/usr/bin/env bash
set -euo pipefail

case "${BROWSER_ENGINE:-chromium}" in
  chromium)
    export BROWSER_AUTORESTART=true BROWSER_STARTRETRIES=3 BROWSER_STOPASGROUP=false BROWSER_STARTSECS=1
    ;;
  cloakbrowser)
    export BROWSER_AUTORESTART=false BROWSER_STARTRETRIES=0 BROWSER_STOPASGROUP=true BROWSER_STARTSECS=0
    /opt/sandbox/cloak-venv/bin/python /opt/sandbox/cloak/cloak_runtime.py prepare
    ;;
  *)
    echo "Unsupported BROWSER_ENGINE; expected chromium or cloakbrowser" >&2
    exit 1
    ;;
esac

exec /usr/bin/supervisord -c /etc/supervisor/conf.d/supervisord.conf
