#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require podman-compose
require curl
[ -x "$PY" ] || fail "venv missing, run scripts/setup.sh first"
mkdir -p "$RUN/logs"

log "starting postgres and qdrant"
compose up -d >/dev/null 2>&1 || fail "podman-compose up failed"
wait_until 60 psql_exec -c "SELECT 1" || fail "postgres not ready, see: podman logs s9-postgres"
wait_until 60 curl -sf "$(service_url qdrant)/readyz" || fail "qdrant not ready, see: podman logs s9-qdrant"

if ! port_up "$(service_port ui)"; then
  log "building the three hnsw indexes and measuring recall and latency"
  "$PY" "$ROOT/app/bench.py" 2>&1 | tee "$RUN/logs/bench.log" || fail "benchmark failed, see .run/logs/bench.log"
  log "starting ui"
  nohup "$PY" "$ROOT/app/server.py" >"$RUN/logs/ui.log" 2>&1 &
  echo $! >"$RUN/ui.pid"
  wait_until 60 curl -sf "$(service_url ui)/api/results" || fail "ui did not answer, see .run/logs/ui.log"
fi

"$SCRIPTS/status.sh" || fail "a service is down"

log "links"
printf "%-18s %s\n" postgres "$(service_url postgres)"
printf "%-18s %s\n" qdrant "$(service_url qdrant)"
printf "%-18s %s\n" qdrant-dashboard "$(service_url qdrant)/dashboard"
printf "%-18s %s\n" ui "$(service_url ui)"
printf "%-18s %s\n" api "$(service_url ui)/api/results"
