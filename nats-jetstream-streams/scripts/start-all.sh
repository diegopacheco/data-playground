#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require podman
require podman-compose
require curl
podman image exists "$APP_IMAGE" || fail "image $APP_IMAGE missing, run scripts/setup.sh first"

log "starting the 3 node nats jetstream cluster"
compose up -d r8-nats-1 r8-nats-2 r8-nats-3 >/dev/null 2>&1 || fail "podman-compose up of the nats nodes failed"
wait_until 60 jetstream_ready || fail "jetstream cluster not ready, see: podman logs r8-nats-1"
log "jetstream cluster up with 3 peers"

log "starting ui"
compose up -d r8-app >/dev/null 2>&1 || fail "podman-compose up r8-app failed"
wait_until 60 curl -sf -o /dev/null "$(service_url ui)/" || fail "ui did not answer, see: podman logs r8-app"
log "ui up on $(service_url ui)"

if [ "$(api results)" = "{}" ]; then
  log "running every scenario once"
  api_post run-all >/dev/null || fail "scenarios failed, see: podman logs r8-app"
fi

"$SCRIPTS/status.sh"

log "links"
for name in $(service_names); do
  printf "%-10s %s\n" "$name" "$(service_url "$name")"
done
printf "%-10s %s\n" results "$(service_url ui)/api/results"
printf "%-10s %s\n" cluster "$(service_url ui)/api/cluster"
