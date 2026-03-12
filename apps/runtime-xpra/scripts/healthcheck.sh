#!/usr/bin/env bash
set -euo pipefail

curl --fail --silent http://127.0.0.1:9222/json/version >/dev/null
curl --fail --silent "http://127.0.0.1:${XPRA_PORT:-14500}/" >/dev/null
curl --fail --silent "http://127.0.0.1:${XPRA_PORT:-14500}/js/lib/jquery.js" >/dev/null
/usr/bin/python3 -c 'import PIL' >/dev/null
xpra info --display="${DISPLAY:-:100}" >/dev/null
