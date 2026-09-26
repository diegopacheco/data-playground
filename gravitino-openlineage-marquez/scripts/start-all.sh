#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require podman
require podman-compose
require curl
podman image exists "$APP_IMAGE" || fail "image $APP_IMAGE missing, run scripts/setup.sh first"

log "starting postgres"
compose up -d r6-postgres >/dev/null 2>&1 || fail "podman-compose up r6-postgres failed"
wait_until 60 pg_ready || fail "postgres not ready, see: podman logs r6-postgres"
log "postgres up on $(service_url postgres)"

log "starting gravitino, marquez and marquez web"
compose up -d --no-deps r6-gravitino r6-marquez r6-marquez-web >/dev/null 2>&1 || fail "podman-compose up failed"
wait_long 2 curl -sf "$(service_url gravitino)/api/version" || fail "gravitino not ready, see: podman logs r6-gravitino"
log "gravitino up on $(service_url gravitino)"
wait_long 3 curl -sf "$(service_url marquez)/api/v1/namespaces" || fail "marquez not ready, see: podman logs r6-marquez"
log "marquez up on $(service_url marquez)"
wait_long 2 curl -sf "$(service_url marquez_web)" || fail "marquez web not ready, see: podman logs r6-marquez-web"
log "marquez web up on $(service_url marquez_web)"

if [ "$(gold_rows)" -gt 0 ]; then
  log "gold.revenue_by_category already holds $(gold_rows) rows, skipping pipeline"
else
  "$SCRIPTS/pipeline.sh"
fi

log "starting ui"
compose up -d --no-deps r6-ui >/dev/null 2>&1 || fail "podman-compose up r6-ui failed"
wait_until 60 curl -sf "$(service_url ui)/api/info" || fail "ui did not answer, see: podman logs r6-ui"
log "ui up on $(service_url ui)"

"$SCRIPTS/status.sh"

log "links"
printf "%-16s %s\n" ui "$(service_url ui)"
printf "%-16s %s\n" gravitino-ui "$(service_url gravitino)/ui"
printf "%-16s %s\n" gravitino-api "$(service_url gravitino)/api/metalakes/$METALAKE"
printf "%-16s %s\n" openlineage-in "$(service_url gravitino)/api/lineage"
printf "%-16s %s\n" marquez-ui "$(service_url marquez_web)"
printf "%-16s %s\n" marquez-api "$(service_url marquez)/api/v1/namespaces/$JOB_NAMESPACE/jobs"
printf "%-16s %s\n" postgres "$(service_url postgres)"
