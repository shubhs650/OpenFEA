#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/common.sh"
check_tools
[[ -x .venv/bin/python ]] || { echo 'BLOCKED: run make setup first' >&2; exit 1; }
[[ "$(.venv/bin/python --version)" == "Python $(cat .python-version)" ]] || { echo 'BLOCKED: incorrect Python version' >&2; exit 1; }
.venv/bin/python scripts/dev/doctor.py "$@"
