#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require podman-compose
[ -d "$ROOT/target/lib" ] || fail "app not built, run ./scripts/setup.sh first"

log "starting tigerbeetle"
podman-compose up -d >"$LOGS/compose.log" 2>&1 || fail "podman-compose up failed, see $LOGS/compose.log"
wait_for 60 tigerbeetle_ready || fail "tigerbeetle not ready, see podman logs $TB_CONTAINER"
log "tigerbeetle up on $(service_url tigerbeetle)"

log "ingesting orders"
run_java ledger.Ingest || fail "ingest failed"

if [ -f "$RUN/bench.json" ]; then
  log "throughput run already recorded in .run/bench.json, delete it to run again"
else
  log "throughput run"
  run_java ledger.Bench || fail "throughput run failed"
fi

start_bg ui "$JAVA_HOME/bin/java" -Xmx256m --enable-native-access=ALL-UNNAMED -cp "$CLASSPATH_APP" ledger.UiServer
wait_port_up "$(service_port ui)" 60 || fail "ui did not open port $(service_port ui), see $LOGS/ui.log"
log "ui up on $(service_url ui)"

"$SCRIPTS/status.sh" || true

log "links"
for name in $(service_names); do
  printf "%-12s %s\n" "$name" "$(service_url "$name")"
done
printf "%-12s %s\n" "api" "$(service_url ui)/api/categories"
