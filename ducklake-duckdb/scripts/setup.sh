#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require podman
require podman-compose
require python3.14
require lsof

if [ ! -x "$PY" ]; then
  log "creating python 3.14 venv"
  python3.14 -m venv "$ROOT/.venv" || fail "venv creation failed"
fi
log "installing python requirements"
"$PY" -m pip install -q -r "$ROOT/requirements.txt" || fail "pip install failed"
log "installing duckdb extensions ducklake, postgres, httpfs"
"$PY" -c 'import duckdb
c = duckdb.connect()
[c.install_extension(e) for e in ("ducklake", "postgres", "httpfs")]' || fail "duckdb extension install failed"
log "pulling images"
podman pull -q docker.io/library/postgres:18.6 >/dev/null || fail "postgres pull failed"
podman pull -q docker.io/pgsty/minio:RELEASE.2026-08-04T00-00-00Z >/dev/null || fail "minio pull failed"
mkdir -p "$RUN/logs"
log "setup done"
