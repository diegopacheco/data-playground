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
podman pull -q docker.io/timescale/timescaledb:2.30.2-pg18 >/dev/null || fail "timescaledb pull failed"
podman pull -q docker.io/questdb/questdb:10.0.1 >/dev/null || fail "questdb pull failed"
podman pull -q docker.io/library/influxdb:3.11.6-core >/dev/null || fail "influxdb 3 core pull failed"
mkdir -p "$RUN/logs" "$ROOT/data"
if [ ! -s "$ROOT/data/readings.csv" ]; then
  log "generating sensor readings into data/readings.csv"
  "$PY" "$ROOT/app/generate.py" || fail "data generation failed"
fi
log "setup done"
