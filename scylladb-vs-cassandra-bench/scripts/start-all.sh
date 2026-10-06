#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require podman-compose
[ -d "$ROOT/target/lib" ] || fail "app not built, run ./scripts/setup.sh first"

log "starting databases"
podman-compose up -d >"$LOGS/compose.log" 2>&1 || fail "podman-compose up failed, see $LOGS/compose.log"

wait_for 60 cql_ready "$SCYLLA_CONTAINER" || fail "scylladb not ready, see podman logs $SCYLLA_CONTAINER"
log "scylladb up on $(service_url scylla)"
wait_for 60 cql_ready "$CASSANDRA_CONTAINER" || wait_for 60 cql_ready "$CASSANDRA_CONTAINER" || fail "cassandra not ready, see podman logs $CASSANDRA_CONTAINER"
log "cassandra up on $(service_url cassandra)"

if [ ! -f "$RESULTS" ] || [ ! -f "$BENCH_CSV" ] || [ "${BENCH_FORCE:-0}" = "1" ]; then
  log "running benchmark"
  run_java bench.Bench 2>&1 | tee "$LOGS/bench.log" || fail "benchmark failed, see $LOGS/bench.log"
else
  log "results.json already present, skipping benchmark (BENCH_FORCE=1 to rerun)"
fi

start_bg ui "$JAVA_HOME/bin/java" -Xmx128m -cp "$CLASSPATH_APP" bench.UiServer
wait_port_up "$(service_port ui)" 60 || fail "ui did not open port $(service_port ui), see $LOGS/ui.log"

"$SCRIPTS/status.sh" || true

log "links"
for name in $(service_names); do
  printf "%-10s %s\n" "$name" "$(service_url "$name")"
done
printf "%-10s %s\n" "api" "$(service_url ui)/api/results"
