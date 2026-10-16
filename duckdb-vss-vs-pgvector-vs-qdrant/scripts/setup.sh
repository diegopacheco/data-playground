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
log "installing duckdb extension vss"
"$PY" -c 'import duckdb
duckdb.connect().install_extension("vss")' || fail "duckdb vss extension install failed"
log "pulling images"
podman pull -q docker.io/pgvector/pgvector:0.8.6-pg18-trixie >/dev/null || fail "pgvector pull failed"
podman pull -q docker.io/qdrant/qdrant:v1.19.2 >/dev/null || fail "qdrant pull failed"
mkdir -p "$RUN/logs"
log "setup done"
