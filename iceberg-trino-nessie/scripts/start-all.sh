#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require podman-compose
require curl

pipeline_done() {
  curl -sf "$(service_url nessie)/api/v2/trees/merged" >/dev/null 2>&1
}

log "starting minio"
compose up -d i4-minio >/dev/null
wait_until 60 curl -sf "$(service_url minio)/minio/health/ready" || fail "minio not ready, see: podman logs i4-minio"
wait_until 60 mc alias set local http://localhost:9000 i4admin i4password || fail "mc alias failed"
log "minio up on $(service_url minio)"

if ! pipeline_done; then
  log "resetting bucket lake and nessie in-memory catalog"
  mc rb --force local/lake >/dev/null 2>&1 || true
  mc mb local/lake >/dev/null || fail "could not create bucket lake"
  compose up -d --force-recreate i4-nessie >/dev/null
fi
compose up -d i4-nessie >/dev/null
wait_until 60 curl -sf "$(service_url nessie)/api/v2/config" || fail "nessie not ready, see: podman logs i4-nessie"
log "nessie up on $(service_url nessie)"

log "starting trino"
compose up -d i4-trino >/dev/null
wait_until 60 trino_ready || fail "trino not ready, see: podman logs i4-trino"
log "trino up on $(service_url trino)"

if ! pipeline_done; then
  log "running the branching pipeline"
  compose run --rm i4-pipeline || fail "pipeline failed"
fi

log "starting ui"
compose up -d i4-ui >/dev/null
wait_until 60 curl -sf "$(service_url ui)/api/refs" || fail "ui api did not answer, see: podman logs i4-ui"
log "ui up on $(service_url ui)"

"$SCRIPTS/status.sh"

log "links"
printf "%-14s %s\n" minio-s3 "$(service_url minio)"
printf "%-14s %s\n" minio-console "$(service_url console)"
printf "%-14s %s\n" nessie-api "$(service_url nessie)/api/v2/trees"
printf "%-14s %s\n" nessie-ui "$(service_url nessie)"
printf "%-14s %s\n" trino "$(service_url trino)/ui/"
printf "%-14s %s\n" ui "$(service_url ui)"
printf "%-14s %s\n" api "$(service_url ui)/api/summary"
