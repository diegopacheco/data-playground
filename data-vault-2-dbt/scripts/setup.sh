#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require python3.14
require lsof
require curl
require awk

if [ ! -x "$PY" ]; then
  log "creating python 3.14 venv"
  python3.14 -m venv "$ROOT/.venv" || fail "venv creation failed"
fi
log "installing python requirements"
"$PY" -m pip install -q -r "$ROOT/requirements.txt" || fail "pip install failed"
"$ROOT/.venv/bin/dbt" --version >/dev/null 2>&1 || fail "dbt does not start"
mkdir -p "$RUN/logs"
log "setup done"
