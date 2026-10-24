#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

log "starting"

require podman-compose
require curl
podman-compose up -d

for name in minio minio-console rest; do
  port="$(service_port "$name")"
  wait_port_up "$port" 60 || fail "$name did not open port $port"
done

wait_for 60 bucket_ready || fail "bucket warehouse was not created, see podman logs $BUCKET_CONTAINER"
log "minio up on $(service_url minio) with bucket warehouse"

wait_for 60 catalog_ready || fail "iceberg rest catalog is not answering"
log "iceberg rest catalog up on $(service_url rest)"

if ! port_up "$(service_port ui)"; then
  run_lake_job
fi

start_bg ui "$ROOT" sbt -batch "lake/runMain UiServer"
wait_port_up "$(service_port ui)" 60 || fail "ui did not open port $(service_port ui), see $LOGS/ui.log"
log "ui up on $(service_url ui)"

"$SCRIPTS/status.sh"

log "links"
for name in $(service_names); do
  printf "%-14s %s\n" "$name" "$(service_url "$name")"
done
printf "%-14s %s\n" "api" "$(service_url ui)/api/snapshots"
