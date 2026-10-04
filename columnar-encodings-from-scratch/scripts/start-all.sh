#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require podman
require podman-compose
require curl
podman image exists "$APP_IMAGE" || fail "image $APP_IMAGE missing, run scripts/setup.sh first"

log "starting r18-app"
compose up -d r18-app >/dev/null 2>&1 || fail "podman-compose up failed"
wait_until 60 curl -sf -o /dev/null "$(service_url ui)/api/health" || fail "app did not answer, see: podman logs r18-app"
log "app up on $(service_url ui), waiting for the benchmark"
wait_until 60 results_ready || fail "benchmark did not finish, see: podman logs r18-app"
log "benchmark done"

"$SCRIPTS/status.sh"

log "links"
printf "%-10s %s\n" ui "$(service_url ui)"
printf "%-10s %s\n" results "$(service_url ui)/api/results"
printf "%-10s %s\n" columns "$(service_url ui)/api/columns"
