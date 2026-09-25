#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

log "starting"

require podman-compose
require java
podman-compose up -d
wait_port_up "$(service_port cassandra)" 60 || fail "cassandra did not open port $(service_port cassandra)"
wait_cql_ready 60 || fail "cassandra did not accept cql within 60 seconds, see podman logs $CASSANDRA_CONTAINER"
log "cassandra up on $(service_url cassandra)"

[ -d "$ROOT/target/lib" ] || build_app
"$SCRIPTS/pipeline.sh"

start_bg ui java -cp "$CLASSPATH_APP" com.github.diegopacheco.flinkcassandra.UiServer
wait_port_up "$(service_port ui)" 60 || fail "ui did not open port $(service_port ui), see $LOGS/ui.log"
log "ui up on $(service_url ui)"

"$SCRIPTS/status.sh"

log "links"
for name in $(service_names); do
  printf "%-14s %s\n" "$name" "$(service_url "$name")"
done
printf "%-14s %s\n" "api" "$(service_url ui)/api/revenue"
