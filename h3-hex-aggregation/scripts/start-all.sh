#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require podman
require podman-compose
require curl
podman image exists "$APP_IMAGE" || fail "image $APP_IMAGE missing, run scripts/setup.sh first"

log "starting $APP_CONTAINER"
compose up -d >/dev/null 2>&1 || fail "podman-compose up failed"
wait_until 60 curl -sf -o /dev/null "$(service_url ui)/api/summary" || fail "ui did not answer, see: podman logs $APP_CONTAINER"
log "ui up on $(service_url ui)"

"$SCRIPTS/status.sh"

log "links"
for name in $(service_names); do
  printf "%-12s %s\n" "$name" "$(service_url "$name")"
done
printf "%-12s %s\n" summary "$(service_url ui)/api/summary"
printf "%-12s %s\n" crosscheck "$(service_url ui)/api/crosscheck"
