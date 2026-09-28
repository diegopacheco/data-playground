#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require podman
require podman-compose
require curl
podman image exists "$APP_IMAGE" || fail "image $APP_IMAGE missing, run scripts/setup.sh first"
data_ready || fail "dataset missing, run scripts/setup.sh first"

log "starting postgres with apache age"
compose up -d r15-age >/dev/null 2>&1 || fail "podman-compose up r15-age failed"
wait_until 60 db_ready || fail "postgres not ready, see: podman logs r15-age"
log "postgres up on $(service_url postgres)"

log "starting app, it loads the SQL tables and the graph on boot"
compose up -d r15-app >/dev/null 2>&1 || fail "podman-compose up r15-app failed"
wait_until 60 app_ready || fail "app did not answer, see: podman logs r15-app"
log "app up on $(service_url ui)"

"$SCRIPTS/status.sh"

log "links"
printf "%-10s %s\n" ui "$(service_url ui)"
printf "%-10s %s\n" api "$(service_url ui)/api/stats"
printf "%-10s %s\n" postgres "$(service_url postgres)"
