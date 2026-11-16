#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require podman
require podman-compose
require curl
podman image exists "$APP_IMAGE" || fail "image $APP_IMAGE missing, run scripts/setup.sh first"

log "starting redpanda and postgres"
compose up -d t5-redpanda t5-postgres >/dev/null 2>&1 || fail "podman-compose up of redpanda and postgres failed"
wait_until 60 redpanda_ready || fail "redpanda not healthy, see: podman logs t5-redpanda"
wait_until 60 postgres_ready || fail "postgres not ready, see: podman logs t5-postgres"
ensure_topic orders-clean 3
ensure_topic orders-dlq 1
log "topics orders-clean (3 partitions) and orders-dlq (1 partition) ready"

log "starting redpanda connect in streams mode"
prepare_out_volume
compose up -d t5-connect >/dev/null 2>&1 || fail "podman-compose up t5-connect failed"
wait_until 60 orders_stream_active || fail "orders stream not active, see: podman logs t5-connect"
wait_until 60 customers_loaded || fail "customers stream did not load the csv, see: podman logs t5-connect"
log "streams orders and customers loaded"

log "starting ui"
compose up -d t5-ui >/dev/null 2>&1 || fail "podman-compose up t5-ui failed"
wait_until 60 curl -sf -o /dev/null "$(service_url ui)/" || fail "ui did not answer, see: podman logs t5-ui"

if [ "$(curl -sf -m 30 "$(service_url ui)/api/runs")" = "[]" ]; then
  log "sending the first seeded batch"
  curl -sf -m 120 -X POST "$(service_url ui)/api/send" >/dev/null || fail "first seeded batch failed, see: podman logs t5-ui"
fi

"$SCRIPTS/status.sh"

log "links"
for name in $(service_names); do
  printf "%-10s %s\n" "$name" "$(service_url "$name")"
done
printf "%-10s %s\n" ingest "$(service_url connect)/orders/ingest"
printf "%-10s %s\n" streams "$(service_url connect)/connect/streams"
printf "%-10s %s\n" metrics "$(service_url connect)/connect/metrics"
