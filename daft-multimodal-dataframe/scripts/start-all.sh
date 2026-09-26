#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require podman
require podman-compose
require curl
require python3
podman image exists "$APP_IMAGE" || fail "image $APP_IMAGE missing, run scripts/setup.sh first"

if output_ready; then
  log "parquet output already in volume $OUTPUT_VOLUME, skipping pipeline"
else
  "$SCRIPTS/pipeline.sh"
fi

log "starting ui"
compose up -d r5-ui >/dev/null 2>&1 || fail "podman-compose up r5-ui failed"
wait_until 60 curl -sf "$(service_url ui)/api/info" || fail "ui did not answer, see: podman logs r5-ui"
log "ui up on $(service_url ui)"

"$SCRIPTS/status.sh"

log "links"
printf "%-10s %s\n" ui "$(service_url ui)"
printf "%-10s %s\n" groupby "$(service_url ui)/#groupby"
printf "%-10s %s\n" pipeline "$(service_url ui)/#pipeline"
printf "%-10s %s\n" info "$(service_url ui)/api/info"
printf "%-10s %s\n" query "$(service_url ui)/api/products?color=red&min_brightness=70&max_price=50"
