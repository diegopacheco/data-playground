#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require podman-compose
require curl
[ -x "$PY" ] || fail "venv missing, run scripts/setup.sh first"
mkdir -p "$RUN/logs"

log "starting clickhouse"
compose up -d >"$RUN/logs/compose.log" 2>&1 || fail "podman-compose up failed, see .run/logs/compose.log"
wait_until 60 clickhouse_ready || fail "clickhouse not ready, see: podman logs $CLICKHOUSE_CONTAINER"

if ! port_up "$(service_port ui)"; then
  log "running the projection vs materialized view benchmark"
  app bench.py || fail "benchmark failed"
  log "starting ui"
  CLICKHOUSE_URL="$(service_url clickhouse)" UI_PORT="$(service_port ui)" RESULTS="$RESULTS" \
    nohup "$PY" "$ROOT/app/server.py" >"$RUN/logs/ui.log" 2>&1 &
  echo $! >"$RUN/ui.pid"
  wait_until 60 curl -sf "$(service_url ui)/api/results" || fail "ui did not answer, see .run/logs/ui.log"
fi

"$SCRIPTS/status.sh" || fail "a service is down"

log "links"
printf "%-14s %s\n" clickhouse "$(service_url clickhouse)"
printf "%-14s %s\n" clickhouse-sql "$(service_url clickhouse)/play"
printf "%-14s %s\n" ui "$(service_url ui)"
printf "%-14s %s\n" api "$(service_url ui)/api/results"
