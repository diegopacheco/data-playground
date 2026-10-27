#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require podman
require podman-compose
require python3.14
require lsof
require curl

if [ ! -x "$PY" ]; then
  log "creating python 3.14 venv"
  python3.14 -m venv "$ROOT/.venv" || fail "venv creation failed"
fi
log "installing python requirements"
"$PY" -m pip install -q -r "$ROOT/requirements.txt" || fail "pip install failed"
log "installing duckdb extensions iceberg, httpfs"
"$PY" -c 'import duckdb
c = duckdb.connect()
[c.install_extension(e) for e in ("iceberg", "httpfs")]' || fail "duckdb extension install failed"
log "pulling images"
podman pull -q docker.io/redpandadata/redpanda:v26.2.3 >/dev/null || fail "redpanda pull failed"
podman pull -q docker.io/apache/iceberg-rest-fixture:1.10.1 >/dev/null || fail "iceberg rest catalog pull failed"
podman pull -q docker.io/pgsty/minio:RELEASE.2026-08-04T00-00-00Z >/dev/null || fail "minio pull failed"
mkdir -p "$RUN/logs"
log "setup done"
