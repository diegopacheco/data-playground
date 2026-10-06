#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require podman
require podman-compose
require curl
podman image exists "$APP_IMAGE" || fail "image $APP_IMAGE missing, run scripts/setup.sh first"
data_ready || fail "dataset missing, run scripts/setup.sh first"
mkdir -p "$ROOT/results"

log "starting app"
compose up -d r17-app >/dev/null 2>&1 || fail "podman-compose up r17-app failed"
wait_until 60 curl -sf -o /dev/null "$(service_url ui)/api/health" || fail "app did not answer, see: podman logs r17-app"
log "app up on $(service_url ui)"

if [ -f "$ROOT/results/results.json" ]; then
  log "results/results.json exists, skipping sketching (run scripts/sketch.sh to rebuild)"
else
  "$SCRIPTS/sketch.sh"
fi

"$SCRIPTS/status.sh"

log "links"
printf "%-10s %s\n" ui "$(service_url ui)"
printf "%-10s %s\n" results "$(service_url ui)/api/results"
printf "%-10s %s\n" merge "$(service_url ui)/api/merge?partitions=0,1,2"
printf "%-10s %s\n" exact "$(service_url ui)/api/exact?partitions=0,1,2"
