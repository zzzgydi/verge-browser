#!/usr/bin/env bash
set -euo pipefail

exec /usr/bin/supervisord -c /etc/supervisor/conf.d/supervisord.conf
