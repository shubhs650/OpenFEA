#!/usr/bin/env bash
set -euo pipefail
if [[ $# -gt 1 || ( $# -eq 1 && "$1" != --prerequisites-only ) ]]; then
  echo 'Usage: setup.sh [--prerequisites-only]' >&2
  exit 2
fi
source "$(dirname "$0")/common.sh"
check_tools
# Locked installs reject stale manifests without updating locks; artifact verification stays enabled.
uv sync --locked --python "$(cat .python-version)"
[[ "$(.venv/bin/python --version)" == "Python $(cat .python-version)" ]] || {
  echo 'BLOCKED: virtual environment Python does not match .python-version' >&2; exit 1;
}
npm ci
# Pinned Playwright installs its matching Chromium headless shell; no privileged OS install.
node_modules/.bin/playwright install chromium --only-shell
.venv/bin/python scripts/native/install.py
if [[ ${1:-} == --prerequisites-only ]]; then
  # Separate CI application job: install/probe the identical pinned tools;
  # the core job runs the complete native regression exactly once.
  bash scripts/codex/check.sh
else
  bash scripts/codex/check.sh --require-native
fi
