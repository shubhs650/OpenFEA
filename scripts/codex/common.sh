#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
export UV_CACHE_DIR="${UV_CACHE_DIR:-$ROOT/.local/cache/uv}"
export npm_config_cache="${npm_config_cache:-$ROOT/.local/cache/npm}"
export PLAYWRIGHT_BROWSERS_PATH="${PLAYWRIGHT_BROWSERS_PATH:-$ROOT/.local/browsers}"
export PYTHONPATH="$ROOT/services/api"
export PATH="$ROOT/.venv/bin:$PATH"

check_tools() {
  local expected actual
  for tool in node npm uv; do
    command -v "$tool" >/dev/null || { echo "BLOCKED: $tool missing; see docs/DEVELOPMENT.md" >&2; return 1; }
  done
  expected="v$(cat .node-version)"
  actual="$(node --version)"
  [[ "$actual" == "$expected" ]] || { echo "BLOCKED: Node $expected required, found $actual" >&2; return 1; }
  actual="$(npm --version)"
  [[ "$actual" == '11.9.0' ]] || { echo "BLOCKED: npm 11.9.0 required, found $actual" >&2; return 1; }
  expected="$(cat .uv-version)"
  actual="$(uv --version | awk '{print $2}')"
  [[ "$actual" == "$expected" ]] || { echo "BLOCKED: uv $expected required, found $actual" >&2; return 1; }
}
