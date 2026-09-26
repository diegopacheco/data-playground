#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require podman
require podman-compose
require curl
require python3
require lsof
podman image exists "$APP_IMAGE" || fail "image $APP_IMAGE missing, run scripts/setup.sh first"

log "starting postgres"
compose up -d r4-postgres >/dev/null 2>&1 || fail "podman-compose up r4-postgres failed"
wait_until 60 podman exec "$PG_CONTAINER" pg_isready -U shop -d shop || fail "postgres not ready, see: podman logs $PG_CONTAINER"
wait_until 60 port_up "$(service_port postgres)" || fail "postgres port $(service_port postgres) not listening"
log "postgres up on $(postgres_url)"

log "starting app (ui, rest source, dlt pipeline)"
compose up -d r4-app >/dev/null 2>&1 || fail "podman-compose up r4-app failed"
wait_until 60 curl -sf "$(service_url ui)/api/overview" || fail "app did not answer, see: podman logs r4-app"
log "app up on $(service_url ui)"

if [ "$(run_count)" = "0" ]; then
  "$SCRIPTS/pipeline.sh"
else
  log "pipeline already ran $(run_count) times, keeping the destination"
fi

"$SCRIPTS/status.sh"

log "links"
printf "%-10s %s\n" ui "$(service_url ui)"
printf "%-10s %s\n" rest "$(service_url ui)/source/customers?page=1&page_size=5"
printf "%-10s %s\n" overview "$(service_url ui)/api/overview"
printf "%-10s %s\n" schema "$(service_url ui)/api/schema"
printf "%-10s %s\n" postgres "$(postgres_url)"
