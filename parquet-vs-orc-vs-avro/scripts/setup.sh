#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

log "setup started"

require python3.14
if [ ! -x "$ROOT/.venv/bin/python" ]; then
  python3.14 -m venv "$ROOT/.venv"
fi
"$ROOT/.venv/bin/pip" install -q -r "$ROOT/requirements.txt" || fail "pip install failed"

log "setup done"
