#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/common.sh"
check_tools
[[ -x .venv/bin/python && -d node_modules ]] || { echo 'BLOCKED: run make setup first' >&2; exit 1; }
exec .venv/bin/python scripts/dev/serve.py "$@"
