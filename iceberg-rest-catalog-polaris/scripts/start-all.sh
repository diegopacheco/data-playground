#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

log "starting"

require podman-compose
require curl
require python3
if ! polaris_ready || ! port_up "$(service_port minio)"; then
  podman-compose up -d i9-minio i9-bucket i9-polaris
fi

for name in minio console polaris health; do
  port="$(service_port "$name")"
  wait_port_up "$port" 60 || fail "$name did not open port $port"
done

wait_for 60 bucket_ready || fail "bucket i9-warehouse was not created, see podman logs $BUCKET_CONTAINER"
log "minio up on $(service_url minio) with bucket i9-warehouse"

wait_for 60 polaris_ready || fail "polaris is not healthy, see podman logs i9-polaris"
log "polaris up on $(service_url polaris)"

log "bootstrapping polaris"
previous="$(load_credential && printf "%s" "$POLARIS_CREDENTIAL" || true)"
"$ROOT/polaris/bootstrap.sh"
load_credential || fail "polaris bootstrap did not write $CREDENTIAL_FILE"

if [ "$previous" != "$POLARIS_CREDENTIAL" ]; then
  log "principal credentials changed, restarting ui"
  stop_bg ui
fi

if [ "$(trino_credential)" != "$POLARIS_CREDENTIAL" ]; then
  podman rm -f "$TRINO_CONTAINER" >/dev/null 2>&1 || true
  podman-compose up -d i9-trino
fi
wait_port_up "$(service_port trino)" 60 || fail "trino did not open port $(service_port trino)"
wait_for 60 trino_ready || fail "trino did not finish starting, see podman logs $TRINO_CONTAINER"
log "trino up on $(service_url trino)"

if ! port_up "$(service_port ui)"; then
  run_pipeline | tee "$LOGS/pipeline.log"
fi

start_bg ui "$ROOT" sbt -batch "app/runMain UiServer"
wait_port_up "$(service_port ui)" 60 || fail "ui did not open port $(service_port ui), see $LOGS/ui.log"
log "ui up on $(service_url ui)"

"$SCRIPTS/status.sh"

log "links"
for name in $(service_names); do
  printf "%-10s %s\n" "$name" "$(service_url "$name")"
done
printf "%-10s %s\n" "api" "$(service_url ui)/api/polaris"
