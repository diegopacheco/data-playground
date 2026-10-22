#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require podman-compose
require curl

log "starting minio"
compose up -d i6-minio >/dev/null
wait_until 60 curl -sf "$(service_url minio)/minio/health/ready" || fail "minio not ready, see: podman logs i6-minio"
wait_until 60 mc alias set local http://localhost:9000 i6admin i6password || fail "mc alias failed"
log "minio up on $(service_url minio)"

if ! curl -sf "$(service_url ui)/api/snapshots" >/dev/null 2>&1; then
  log "starting iceberg rest catalog"
  compose up -d --force-recreate --no-deps i6-rest >/dev/null
  wait_until 60 curl -sf "$(service_url rest)/v1/config" || fail "rest catalog not ready, see: podman logs i6-rest"
  log "recreating bucket warehouse and running the pyiceberg pipeline"
  mc rb --force local/warehouse >/dev/null 2>&1 || true
  mc mb local/warehouse >/dev/null || fail "could not create bucket warehouse"
  compose run --rm i6-pipeline || fail "pipeline failed"
  log "starting ui"
  compose up -d i6-ui >/dev/null
  wait_until 60 curl -sf "$(service_url ui)/api/snapshots" || fail "ui api did not answer, see: podman logs i6-ui"
fi
log "ui up on $(service_url ui)"

"$SCRIPTS/status.sh"

log "links"
printf "%-14s %s\n" minio-s3 "$(service_url minio)"
printf "%-14s %s\n" minio-console "$(service_url console)"
printf "%-14s %s\n" rest-catalog "$(service_url rest)/v1/config"
printf "%-14s %s\n" ui "$(service_url ui)"
printf "%-14s %s\n" api "$(service_url ui)/api/snapshots"
