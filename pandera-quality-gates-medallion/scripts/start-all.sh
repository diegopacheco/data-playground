#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require podman
require podman-compose
require curl
podman image exists "$APP_IMAGE" || fail "image $APP_IMAGE missing, run scripts/setup.sh first"
data_ready || fail "incoming batches missing, run scripts/setup.sh first"

log "starting the pipeline and ui"
compose up -d r12-app >/dev/null 2>&1 || fail "podman-compose up r12-app failed"
wait_until 60 curl -sf -o /dev/null "$(service_url ui)/api/health" || fail "ui did not answer, see: podman logs r12-app"
podman logs r12-app 2>&1 | grep -e '^batch-' -e '^layers' || true

"$SCRIPTS/status.sh"

log "links"
printf "%-10s %s\n" ui "$(service_url ui)"
printf "%-10s %s\n" api "$(service_url ui)/api/summary"
