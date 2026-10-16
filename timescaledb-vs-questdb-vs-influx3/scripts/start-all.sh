#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require podman-compose
require curl
[ -x "$PY" ] || fail "venv missing, run scripts/setup.sh first"
[ -s "$ROOT/data/readings.csv" ] || fail "data/readings.csv missing, run scripts/setup.sh first"
mkdir -p "$RUN/logs"
export_ports

if ! port_up "$(service_port ui)"; then
  log "recreating timescaledb, questdb and influxdb 3 core with empty volumes"
  compose down >/dev/null 2>&1 || true
  for volume in s7-timescaledb-data s7-questdb-data s7-influx3-data; do
    podman volume rm "$volume" >/dev/null 2>&1 || true
  done
  compose up -d >/dev/null 2>&1 || fail "podman-compose up failed"
  wait_until 60 podman exec s7-timescaledb psql -U s7 -d s7 -h localhost -c "SELECT 1" || fail "timescaledb not ready, see: podman logs s7-timescaledb"
  wait_until 60 curl -sf "$(service_url questdb)/exec?query=SELECT%201" || fail "questdb not ready, see: podman logs s7-questdb"
  wait_until 60 curl -sf "$(service_url influx3)/health" || fail "influxdb 3 core not ready, see: podman logs s7-influx3"
  log "loading the same readings into the three engines and measuring, this takes a few minutes"
  "$PY" "$ROOT/app/pipeline.py" 2>&1 | tee "$RUN/logs/pipeline.log" || fail "pipeline failed, see .run/logs/pipeline.log"
  log "starting ui"
  nohup "$PY" "$ROOT/app/server.py" >"$RUN/logs/ui.log" 2>&1 &
  echo $! >"$RUN/ui.pid"
  wait_until 60 curl -sf "$(service_url ui)/api/results" || fail "ui did not answer, see .run/logs/ui.log"
fi

"$SCRIPTS/status.sh" || fail "a service is down"

log "links"
printf "%-14s %s\n" timescaledb "$(service_url timescaledb)"
printf "%-14s %s\n" questdb "$(service_url questdb)"
printf "%-14s %s\n" influx3 "$(service_url influx3)/health"
printf "%-14s %s\n" ui "$(service_url ui)"
printf "%-14s %s\n" api "$(service_url ui)/api/results"
