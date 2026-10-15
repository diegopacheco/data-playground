#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require podman-compose
require curl
[ -x "$PY" ] || fail "venv missing, run scripts/setup.sh first"
mkdir -p "$RUN/logs"

if ! port_up "$(service_port ui)"; then
  log "starting postgres, kafka and debezium connect from a clean state"
  compose down -v >/dev/null 2>&1 || true
  compose up -d >"$RUN/logs/compose.log" 2>&1 || fail "podman-compose up failed, see .run/logs/compose.log"
  wait_until 60 psql_exec -c "SELECT count(*) FROM outbox" || fail "postgres not ready, see: podman logs s3-postgres"
  wait_until 60 kafka_tool kafka-topics --list || fail "kafka not ready, see: podman logs s3-kafka"
  wait_until 60 curl -sf "$(service_url connect)/connectors" || wait_until 60 curl -sf "$(service_url connect)/connectors" || fail "kafka connect not ready, see: podman logs s3-connect"
  log "registering debezium connector $CONNECTOR with the outbox event router"
  curl -sf -X PUT -H "Content-Type: application/json" --data @"$ROOT/connect/outbox-connector.json" \
    "$(service_url connect)/connectors/$CONNECTOR/config" >"$RUN/logs/connector.json" || fail "connector registration failed"
  wait_until 60 connector_running || fail "connector $CONNECTOR not running, see $(service_url connect)/connectors/$CONNECTOR/status"
  log "running scenarios"
  "$PY" "$ROOT/app/scenarios.py" || fail "scenarios failed"
  log "starting ui"
  nohup "$PY" "$ROOT/app/server.py" >"$RUN/logs/ui.log" 2>&1 &
  echo $! >"$RUN/ui.pid"
  wait_until 60 curl -sf "$(service_url ui)/api/facts" || fail "ui did not answer, see .run/logs/ui.log"
fi

"$SCRIPTS/status.sh" || fail "a service is down"

log "links"
printf "%-14s %s\n" postgres "$(service_url postgres)"
printf "%-14s %s\n" kafka "$(service_url kafka)"
printf "%-14s %s\n" connect "$(service_url connect)/connectors/$CONNECTOR/status"
printf "%-14s %s\n" ui "$(service_url ui)"
printf "%-14s %s\n" api "$(service_url ui)/api/proof"
