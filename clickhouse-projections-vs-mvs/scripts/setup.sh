#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require podman
require podman-compose
require python3.14
require lsof
require curl
require awk

if [ ! -x "$PY" ]; then
  log "creating python 3.14 venv"
  python3.14 -m venv "$ROOT/.venv" || fail "venv creation failed"
fi
log "python $("$PY" -c 'import platform; print(platform.python_version())'), standard library only"
log "pulling images"
podman pull -q docker.io/clickhouse/clickhouse-server:26.9.2.8 >/dev/null || fail "clickhouse pull failed"
mkdir -p "$RUN/logs"
log "setup done"
