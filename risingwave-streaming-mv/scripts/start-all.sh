#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require podman
require podman-compose
require curl
podman image exists "$APP_IMAGE" || fail "image $APP_IMAGE missing, run scripts/setup.sh first"

log "starting redpanda"
compose up -d t1-redpanda >/dev/null 2>&1 || fail "podman-compose up t1-redpanda failed"
wait_until 60 redpanda_ready || fail "redpanda not ready, see: podman logs t1-redpanda"
log "redpanda ready"

log "starting risingwave single node and the app"
compose up -d t1-risingwave t1-app >/dev/null 2>&1 || fail "podman-compose up of risingwave and the app failed"
wait_until 60 risingwave_ready || fail "risingwave not answering sql, see: podman logs t1-risingwave"
log "risingwave ready"
wait_until 60 curl -sf -o /dev/null "$(service_url ui)/" || fail "ui did not answer, see: podman logs t1-app"
log "ui up on $(service_url ui)"

if api snapshots | grep -q '"phase": "empty"'; then
  log "running the seeded scenario once"
  api_post run-all >/dev/null || fail "scenario failed, see: podman logs t1-app"
fi

"$SCRIPTS/status.sh"

log "links"
for name in $(service_names); do
  printf "%-11s %s\n" "$name" "$(service_url "$name")"
done
printf "%-11s %s\n" live "$(service_url ui)/api/live"
printf "%-11s %s\n" sink "$(service_url ui)/api/sink"
