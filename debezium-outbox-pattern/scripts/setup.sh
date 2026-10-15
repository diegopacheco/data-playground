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
log "pulling images"
podman pull -q docker.io/library/postgres:18.6 >/dev/null || fail "postgres pull failed"
podman pull -q docker.io/apache/kafka:4.3.1 >/dev/null || fail "kafka pull failed"
podman pull -q quay.io/debezium/connect:3.6.3.Final >/dev/null || fail "debezium connect pull failed"
mkdir -p "$RUN/logs"
log "setup done"
