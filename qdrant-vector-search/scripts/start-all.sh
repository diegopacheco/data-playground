#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require podman
require podman-compose
require curl
require python3
podman image exists "$APP_IMAGE" || fail "image $APP_IMAGE missing, run scripts/setup.sh first"

log "starting qdrant"
compose up -d q6-qdrant >/dev/null 2>&1 || fail "podman-compose up q6-qdrant failed"
wait_until 60 curl -sf "$(service_url qdrant)/readyz" || fail "qdrant not ready, see: podman logs q6-qdrant"
log "qdrant up on $(service_url qdrant)"

if [ "$(point_count 2>/dev/null || echo 0)" = "$(csv_rows)" ]; then
  log "collection already holds $(csv_rows) points, skipping pipeline"
else
  "$SCRIPTS/pipeline.sh"
fi

log "starting ui"
compose up -d q6-ui >/dev/null 2>&1 || fail "podman-compose up q6-ui failed"
wait_until 60 curl -sf "$(service_url ui)/api/info" || fail "ui did not answer, see: podman logs q6-ui"
log "ui up on $(service_url ui)"

"$SCRIPTS/status.sh"

log "links"
printf "%-10s %s\n" ui "$(service_url ui)"
printf "%-10s %s\n" dashboard "$(service_url qdrant)/dashboard"
printf "%-10s %s\n" qdrant "$(service_url qdrant)/collections/products"
printf "%-10s %s\n" search "$(service_url ui)/api/search?q=keep+my+coffee+hot&mode=semantic"
