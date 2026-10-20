#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

log "starting"

require podman-compose
require java
podman-compose up -d
wait_port_up "$(service_port postgres)" 60 || fail "postgres did not open port $(service_port postgres)"
wait_pg_ready 60 || fail "postgres orders table not ready, see podman logs $PG_CONTAINER"
log "postgres up on $(service_url postgres) with $(psql_run -tAc 'SELECT count(*) FROM orders') orders"

[ -d "$ROOT/target/lib" ] || build_app

start_bg flink java $JAVA_FLAGS -cp "$CLASSPATH_APP" com.github.diegopacheco.cdciceberg.CdcPipeline
wait_port_up "$(service_port flink)" 60 || fail "flink pipeline did not open port $(service_port flink), see $LOGS/flink.log"
log "flink cdc pipeline up on $(service_url flink)"
start_bg ui java $JAVA_FLAGS -cp "$CLASSPATH_APP" com.github.diegopacheco.cdciceberg.UiServer
wait_port_up "$(service_port ui)" 60 || fail "ui did not open port $(service_port ui), see $LOGS/ui.log"
log "ui up on $(service_url ui)"

wait_in_sync 60 || fail "iceberg did not catch up with postgres within 60 seconds, see $LOGS/flink.log"
pid_alive flink || fail "pipeline died, see $LOGS/flink.log"
log "initial snapshot landed in iceberg, postgres and iceberg are in sync"

"$SCRIPTS/status.sh"

log "links"
for name in $(service_names); do
  printf "%-14s %s\n" "$name" "$(service_url "$name")"
done
printf "%-14s %s\n" "api" "$(service_url ui)/api/compare"
printf "%-14s %s\n" "flink jobs" "$(service_url flink)/jobs/overview"
