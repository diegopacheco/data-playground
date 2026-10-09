#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require podman-compose
require curl

log "starting minio"
compose up -d i5-minio >/dev/null
wait_until 60 curl -sf "$(service_url minio)/minio/health/ready" || fail "minio not ready, see: podman logs i5-minio"
wait_until 60 mc alias set local http://localhost:9000 i5admin i5password || fail "mc alias failed"
log "minio up on $(service_url minio)"

if ! curl -sf "$(service_url ui)/api/revenue" >/dev/null 2>&1; then
  log "recreating bucket lake and running the delta-rs pipeline"
  mc rb --force local/lake >/dev/null 2>&1 || true
  mc mb local/lake >/dev/null || fail "could not create bucket lake"
  compose run --rm i5-pipeline || fail "pipeline failed"
  log "starting ui"
  compose up -d i5-ui >/dev/null
  wait_until 60 curl -sf "$(service_url ui)/api/revenue" || fail "ui api did not answer, see: podman logs i5-ui"
fi
log "ui up on $(service_url ui)"

"$SCRIPTS/status.sh"

log "links"
printf "%-14s %s\n" minio-s3 "$(service_url minio)"
printf "%-14s %s\n" minio-console "$(service_url console)"
printf "%-14s %s\n" ui "$(service_url ui)"
printf "%-14s %s\n" api "$(service_url ui)/api/versions"
