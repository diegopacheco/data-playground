#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require podman-compose
require curl

log "starting paradedb and ui"
compose up -d >"$LOGS/compose-up.log" 2>&1 || fail "podman-compose up failed, see .run/logs/compose-up.log"
wait_until 60 psql_exec -tAc "select 1" || fail "paradedb not ready, see: podman logs $DB_CONTAINER"
log "postgres up on $(service_url postgres)"

loaded="$(psql_exec -tAc "select count(*) from pg_indexes where indexname in ('products_search', 'orders_search')")"
if [ "$loaded" != "2" ]; then
  "$SCRIPTS/pipeline.sh"
else
  log "data already loaded, skipping pipeline"
fi

wait_until 60 api /api/analytics || fail "ui did not answer, see: podman logs q5-ui"
log "ui up on $(service_url ui)"

"$SCRIPTS/status.sh"

log "links"
printf "%-10s %s\n" postgres "$(service_url postgres)"
printf "%-10s %s\n" ui "$(service_url ui)"
printf "%-10s %s\n" search "$(service_url ui)/api/search?q=wireless+noise+cancelling"
printf "%-10s %s\n" analytics "$(service_url ui)/api/analytics"
