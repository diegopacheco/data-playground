#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

log "starting"

require podman-compose
podman info >/dev/null 2>&1 || fail "podman is not reachable, start the podman machine"
podman-compose up -d

for name in minio console; do
  port="$(service_port "$name")"
  wait_port_up "$port" 60 || fail "$name did not open port $port"
done

wait_for 60 minio_ready || fail "minio is not ready"
mc mb --ignore-existing "local/$BUCKET" >/dev/null || fail "could not create bucket $BUCKET"
log "minio up on $(service_url minio) with bucket $BUCKET"

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
printf "%-14s %s\n" "table" "$TABLE_PATH"
