#!/usr/bin/env bash
# Purpose: Run the most useful human smoke flow end to end: create a sandbox, save screenshots, validate files, and print a session URL.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

"$SCRIPT_DIR/create-sandbox.sh"
echo
"$SCRIPT_DIR/browser-smoke.sh"
echo
"$SCRIPT_DIR/files-smoke.sh"
echo
"$SCRIPT_DIR/get-session-url.sh"
