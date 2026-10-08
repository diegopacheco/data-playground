#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

log "setup started"
require podman
require podman-compose
require curl
require awk
require lsof
require "$PYTHON"

podman-compose pull >"$LOGS/pull.log" 2>&1 || fail "image pull failed, see $LOGS/pull.log"
[ "$(csv_rows)" -gt 0 ] || fail "no orders in $CSV"

log "python $("$PYTHON" -c 'import platform; print(platform.python_version())')"
log "setup done"
