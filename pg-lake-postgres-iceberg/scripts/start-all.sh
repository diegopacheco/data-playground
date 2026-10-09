#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require podman
require podman-compose
require curl
podman image exists "$PGLAKE_IMAGE" || fail "image $PGLAKE_IMAGE missing, run scripts/setup.sh first"
podman image exists "$APP_IMAGE" || fail "image $APP_IMAGE missing, run scripts/setup.sh first"
data_ready || fail "dataset missing, run scripts/setup.sh first"

log "starting minio and postgres with pg_lake"
compose up -d r11-minio r11-pglake >/dev/null 2>&1 || fail "podman-compose up r11-minio r11-pglake failed"
wait_until 60 curl -sf "$(service_url minio)/minio/health/live" || fail "minio not ready, see: podman logs r11-minio"
log "minio up on $(service_url minio)"
wait_until 60 pg_ready || fail "postgres not ready, see: podman logs r11-pglake"
wait_until 60 duck_ready || fail "pgduck_server socket missing, see: podman logs r11-pglake"
log "postgres up on $(service_url postgres)"

log "starting ui"
compose up -d r11-app >/dev/null 2>&1 || fail "podman-compose up r11-app failed"
wait_until 60 api status || fail "ui did not answer, see: podman logs r11-app"
log "ui up on $(service_url ui)"

if api lake | grep -q '"table_name": "orders"'; then
  log "iceberg table orders already exists, skipping the pipeline (POST /api/run to rerun)"
else
  log "running the pipeline: reset, load batch 1, load batch 2, delete cancelled"
  api_post run >/dev/null || fail "pipeline failed, see: podman logs r11-app"
fi

"$SCRIPTS/status.sh"

log "links"
for name in $(service_names); do
  printf "%-10s %s\n" "$name" "$(service_url "$name")"
done
printf "%-10s %s\n" api "$(service_url ui)/api/status"
