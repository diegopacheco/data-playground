#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require podman-compose
log "starting"
podman-compose up -d >"$LOGS/compose-up.log" 2>&1 || fail "podman-compose up failed, see $LOGS/compose-up.log"

wait_cmd 60 cassandra_ready || fail "cassandra did not become ready"
log "cassandra up on $(service_url cassandra)"

wait_cmd 60 http_ok "$(service_url airflow)/api/v2/monitor/health" || fail "airflow did not become ready, see podman logs $AIRFLOW_CONTAINER"
log "airflow up on $(service_url airflow)"

wait_cmd 30 http_ok "$(service_url ui)/" || fail "ui did not become ready, see podman logs p4-ui"
log "ui up on $(service_url ui)"

"$SCRIPTS/status.sh" || true

log "links"
for name in $(service_names); do
  printf "%-10s %s\n" "$name" "$(service_url "$name")"
done
printf "%-10s %s\n" "api" "$(service_url ui)/api/revenue"
