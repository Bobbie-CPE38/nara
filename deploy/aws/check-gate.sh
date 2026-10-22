#!/usr/bin/env bash
# AU4 external preflight; Python keeps JSON checks and cookie handling out of shell.
# Usage: check-gate.sh <base url> <Basic user> [Basic password] [--require-real-line] [--staff-id ID]
# --staff-id prompts privately for a web-account password and checks that account's scope.
set -euo pipefail
exec python3 "$(dirname "$0")/check_gate.py" "$@"
