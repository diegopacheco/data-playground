#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require python3.14
require lsof
require awk
[ -x "$PY" ] || python3.14 -m venv "$VENV" || fail "venv creation failed"
"$PY" -m pip install -q --upgrade pip || fail "pip upgrade failed"
"$PY" -m pip install -q -r "$ROOT/requirements.txt" || fail "dependency install failed"
if [ -f "$ROOT/data/orders.parquet" ] && [ -f "$ROOT/data/products.parquet" ]; then
  log "dataset already present"
else
  "$PY" "$ROOT/src/gen.py" || fail "dataset generation failed"
fi
log "setup done"
