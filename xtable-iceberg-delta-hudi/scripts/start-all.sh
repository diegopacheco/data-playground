#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require podman-compose
require curl

port="$(service_port ui)"
if port_up "$port"; then
  log "already running"
  log "ui   $(service_url ui)"
  log "api  $(service_url ui)/api/readers"
  exit 0
fi

[ -f "$XTABLE_JAR" ] || fail "missing $XTABLE_JAR, run scripts/setup.sh first"
[ -f "$ROOT/spark/target/lake-jobs.jar" ] || fail "missing spark jobs jar, run scripts/setup.sh first"

rm -rf "$LAKE_TABLE"
mkdir -p "$ROOT/lake" "$RESULTS_DIR"
rm -f "$RESULTS_DIR"/*.tsv "$RESULTS_DIR"/*.txt
: >"$LOGS/pipeline.log"

step "spark writes orders as a hudi table" writer
step "list table files before sync" files files before
step "xtable sync hudi to delta and iceberg" xtable
step "list table files after sync" files files after
step "spark reads hudi, delta and iceberg" reader

podman-compose up -d ui >"$LOGS/start.log" 2>&1 || fail "podman-compose up failed, see $LOGS/start.log"
wait_port_up "$port" 60 || fail "ui did not open port $port"
wait_for 60 curl -sf "$(service_url ui)/api/readers" || fail "ui is not answering on $(service_url ui)"

log "ui   $(service_url ui)"
log "api  $(service_url ui)/api/readers"
log "api  $(service_url ui)/api/expected"
log "api  $(service_url ui)/api/files"
