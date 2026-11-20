#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require podman
require podman-compose
require curl
podman image exists "$APP_IMAGE" || fail "image $APP_IMAGE missing, run scripts/setup.sh first"

log "starting the libsql primary (sqld)"
compose up -d t6-sqld >/dev/null 2>&1 || fail "podman-compose up t6-sqld failed"
wait_until 60 primary_ready || fail "sqld did not answer /health, see: podman logs t6-sqld"
log "primary up on $(service_url primary)"

log "starting 3 app processes with embedded replicas"
compose up -d t6-replica-1 t6-replica-2 t6-replica-3 >/dev/null 2>&1 || fail "podman-compose up of the replicas failed"
wait_until 60 replicas_ready || fail "replicas did not open, see: podman logs t6-replica-1"

log "starting the console"
compose up -d t6-console >/dev/null 2>&1 || fail "podman-compose up t6-console failed"
wait_until 60 curl -sf -o /dev/null "$(service_url ui)/" || fail "console did not answer, see: podman logs t6-console"

if [ "$(api results)" = '{"outage":{}}' ]; then
  log "running every scenario once"
  api_post run-all >/dev/null || fail "scenarios failed, see: podman logs t6-console"
fi

"$SCRIPTS/status.sh"

log "links"
for name in $(service_names); do
  printf "%-10s %s\n" "$name" "$(service_url "$name")"
done
printf "%-10s %s\n" results "$(service_url ui)/api/results"
printf "%-10s %s\n" topology "$(service_url ui)/api/topology"
