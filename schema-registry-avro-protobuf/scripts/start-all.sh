#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require podman
require podman-compose
require curl
require lsof
podman image exists "$APP_IMAGE" || fail "image $APP_IMAGE missing, run scripts/setup.sh first"

log "starting kafka, apicurio registry and the app"
compose up -d >/dev/null 2>&1 || fail "podman-compose up failed"
wait_until 60 registry_ready || fail "apicurio registry did not answer, see: podman logs r10-registry"
log "registry up on $(service_url registry)"
wait_until 60 kafka_ready || fail "kafka did not answer, see: podman logs r10-kafka"
log "kafka up on $(service_url kafka)"
wait_until 60 api status || fail "app did not answer, see: podman logs r10-app"
log "app up on $(service_url ui)"

if [ "$(api status | python3 -c 'import json,sys; print(json.load(sys.stdin)["ran_at"])')" = "None" ]; then
  log "running the compatibility matrix and the producer and consumer flow"
  api_post run >/dev/null || fail "POST /api/run failed, see: podman logs r10-app"
else
  log "results already in memory, skipping run (POST /api/run to rerun)"
fi

"$SCRIPTS/status.sh"

log "links"
printf "%-10s %s\n" ui "$(service_url ui)"
printf "%-10s %s\n" registry "$(service_url registry)"
printf "%-10s %s\n" kafka "$(service_url kafka)"
printf "%-10s %s\n" matrix "$(service_url ui)/api/matrix"
printf "%-10s %s\n" flow "$(service_url ui)/api/flow"
