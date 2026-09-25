#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

log "starting"

require podman-compose
podman-compose up -d

for name in cassandra redpanda; do
  port="$(service_port "$name")"
  wait_port_up "$port" 60 || fail "$name did not open port $port"
done

wait_for 60 redpanda_ready || fail "redpanda is not healthy"
log "redpanda up on $(service_url redpanda)"

wait_for 60 cql_ready || fail "cassandra is not accepting cql"
podman exec -i "$CASSANDRA_CONTAINER" cqlsh <"$ROOT/cassandra/schema.cql" || fail "schema creation failed"
log "cassandra up on $(service_url cassandra)"

require sbt
start_bg ui "$ROOT" sbt -batch ui/run
wait_port_up "$(service_port ui)" 60 || fail "ui did not open port $(service_port ui), see $LOGS/ui.log"
log "ui up on $(service_url ui)"

"$SCRIPTS/status.sh"

log "links"
for name in $(service_names); do
  printf "%-14s %s\n" "$name" "$(service_url "$name")"
done
printf "%-14s %s\n" "api" "$(service_url ui)/api/revenue"
