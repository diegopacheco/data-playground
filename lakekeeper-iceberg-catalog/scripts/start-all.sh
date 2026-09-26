#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require podman-compose
require curl

log "starting minio and postgres"
compose up -d q4-minio q4-postgres >/dev/null
wait_until 60 curl -sf "$(service_url minio)/minio/health/ready" || fail "minio not ready, see: podman logs q4-minio"
wait_until 60 mc alias set local http://localhost:9000 q4admin q4password || fail "mc alias failed"
mc mb --ignore-existing "local/$BUCKET" >/dev/null || fail "could not create bucket $BUCKET"
wait_until 60 pg_ready || fail "postgres not ready, see: podman logs q4-postgres"
log "minio up on $(service_url minio), postgres up on $(service_url postgres)"

log "running lakekeeper database migrations"
compose run -T --rm q4-migrate >/dev/null || fail "lakekeeper migrate failed"

log "starting lakekeeper"
compose up -d --no-deps q4-lakekeeper >/dev/null
wait_until 60 curl -sf "$(service_url lakekeeper)/health" || fail "lakekeeper not healthy, see: podman logs q4-lakekeeper"
log "lakekeeper up on $(service_url lakekeeper)"

if ! curl -sf "$(service_url ui)/api/revenue" >/dev/null 2>&1; then
  log "bootstrapping lakekeeper, creating warehouse and writing the iceberg table"
  compose run -T --rm q4-pipeline || fail "pipeline failed"
  log "starting ui"
  compose up -d --no-deps q4-ui >/dev/null
  wait_until 60 curl -sf "$(service_url ui)/api/revenue" || fail "ui api did not answer, see: podman logs q4-ui"
fi
log "ui up on $(service_url ui)"

"$SCRIPTS/status.sh"

log "links"
printf "%-16s %s\n" minio-s3 "$(service_url minio)"
printf "%-16s %s\n" minio-console "$(service_url console)"
printf "%-16s %s\n" postgres "$(service_url postgres)"
printf "%-16s %s\n" lakekeeper-ui "$(service_url lakekeeper)/ui"
printf "%-16s %s\n" lakekeeper-api "$(service_url lakekeeper)/management/v1/info"
printf "%-16s %s\n" iceberg-rest "$(service_url lakekeeper)/catalog/v1/config?warehouse=$BUCKET"
printf "%-16s %s\n" swagger "$(service_url lakekeeper)/swagger-ui"
printf "%-16s %s\n" ui "$(service_url ui)"
printf "%-16s %s\n" api "$(service_url ui)/api/catalog"
