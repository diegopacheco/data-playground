#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

podman image exists "$IMAGE" || "$SCRIPTS/setup.sh"
mkdir -p "$ROOT/lake"

podman-compose -f "$ROOT/podman-compose.yml" up -d >"$LOGS/compose-up.log" 2>&1 || fail "podman-compose up failed, see $LOGS/compose-up.log"

wait_cmd 60 http_ok "$(service_url dagster)/server_info" || fail "dagster webserver did not come up on $(service_url dagster)"
wait_cmd 60 http_ok "$(service_url ui)/" || fail "results ui did not come up on $(service_url ui)"

if ! http_ok "$(service_url ui)/api/revenue"; then
  log "materializing assets"
  podman exec "$DAGSTER_CONTAINER" dagster asset materialize --select '*' -m "$DEFS_MODULE" >"$LOGS/materialize.log" 2>&1 || fail "materialization failed, see $LOGS/materialize.log"
fi

log "dagster ui : $(service_url dagster)"
log "results ui : $(service_url ui)"
log "revenue api: $(service_url ui)/api/revenue"
log "tables api : $(service_url ui)/api/tables"
