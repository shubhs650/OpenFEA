#!/usr/bin/env bash
set -euo pipefail
echo "BLOCKED: $1 is not implemented; requires $2. No checks executed." >&2
exit 2
