#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require podman
require podman-compose
require curl
require python3
podman image exists "$APP_IMAGE" || fail "image $APP_IMAGE missing, run scripts/setup.sh first"

log "starting zookeeper, fluss coordinator, fluss tablet server and the flink app"
compose up -d >/dev/null 2>&1 || fail "podman-compose up failed"
wait_until 60 api status || fail "app did not answer, see: podman logs r1-app"
log "app up on $(service_url ui), tiering job $(api status | json_field tiering.status)"
wait_until 60 curl -sf -m 2 "$(service_url flink)/jobs/overview" || fail "flink web ui did not answer on $(service_url flink)"

if [ "$(api fluss | json_field totals.orders)" = "0" ]; then
  log "fluss table is empty, streaming data/orders.csv"
  api_post "ingest?file=orders.csv" >/dev/null || fail "ingest of orders.csv failed"
  log "waiting for the tiering service to commit the first paimon snapshot"
  wait_until 60 lake_ready || fail "no paimon snapshot after 60 tries, see: podman logs r1-app"
else
  log "fluss table already holds data, skipping ingest"
fi

"$SCRIPTS/status.sh"

log "links"
printf "%-10s %s\n" ui "$(service_url ui)"
printf "%-10s %s\n" flink "$(service_url flink)"
printf "%-10s %s\n" status "$(service_url ui)/api/status"
printf "%-10s %s\n" lookup "$(service_url ui)/api/lookup?id=1006"
printf "%-10s %s\n" union "$(service_url ui)/api/union"
