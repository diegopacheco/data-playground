#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require podman-compose
require curl
[ -f "$DATASET" ] || fail "data/dataset.csv missing, run ./scripts/setup.sh first"
podman image exists "$IMAGE" || fail "$IMAGE missing, run ./scripts/setup.sh first"
podman image exists "$TIKV_IMAGE" || fail "$TIKV_IMAGE missing, run ./scripts/setup.sh first"

log "starting pd, tikv, scylladb and foundationdb"
compose up -d >"$LOGS/compose.log" 2>&1 || fail "podman-compose up failed, see .run/logs/compose.log"

wait_until 60 tikv_ready || fail "tikv store not Up in pd, see: podman logs s6-tikv"
log "tikv up, registered in pd"
wait_until 60 scylla_ready || wait_until 60 scylla_ready || fail "scylladb not ready, see: podman logs s6-scylla"
log "scylladb up"
wait_until 60 foundationdb_ready || fail "foundationdb not available, see: podman logs s6-foundationdb"
log "foundationdb up"

for store in $STORES; do
  [ "$(limits "$store")" = "$(limits tikv)" ] || fail "$store limits differ from tikv: $(limits "$store")"
done
log "every store container runs with $(limits tikv)"

if [ ! -f "$RESULTS" ] || [ "${BENCH_FORCE:-0}" = "1" ]; then
  log "running benchmark"
  run_bench 2>&1 | tee "$LOGS/bench.log" || fail "benchmark failed, see .run/logs/bench.log"
else
  log "results.json already present, skipping benchmark (BENCH_FORCE=1 to rerun)"
fi

if ! port_up "$(service_port ui)"; then
  log "starting ui"
  start_ui >"$LOGS/ui.log" 2>&1 || fail "ui container failed, see .run/logs/ui.log"
fi
wait_until 60 curl -sf "$(service_url ui)/api/results" || fail "ui did not answer, see: podman logs s6-ui"

"$SCRIPTS/status.sh" || fail "a service is down"

log "links"
for name in $(service_names); do
  printf "%-13s %s\n" "$name" "$(service_url "$name")"
done
printf "%-13s %s\n" "api" "$(service_url ui)/api/results"
