#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

[ -f "$RUN/vault.duckdb" ] || fail "vault database missing, run scripts/start-all.sh first"
exec "$PY" "$ROOT/app/console.py" "$@"
