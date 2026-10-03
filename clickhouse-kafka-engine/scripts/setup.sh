#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require podman
require podman-compose
require lsof
require "$PYTHON"
[ -f "$CSV" ] || fail "missing $CSV"

log "python $("$PYTHON" -c 'import platform; print(platform.python_version())')"
log "pulling images"
podman-compose pull >"$LOGS/pull.log" 2>&1 || fail "image pull failed, see $LOGS/pull.log"
log "setup done"
