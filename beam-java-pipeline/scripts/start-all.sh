#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require podman-compose
require curl

log "starting postgres"
compose up -d q2-postgres >/dev/null
wait_port_up "$(service_port postgres)" 60 || fail "postgres did not open port $(service_port postgres)"
wait_until 60 postgres_ready || fail "postgres schema not ready, see: podman logs $POSTGRES_CONTAINER"
log "postgres up on $(service_url postgres)"

"$SCRIPTS/pipeline.sh"

log "starting ui"
compose up -d q2-ui >/dev/null
wait_port_up "$(service_port ui)" 60 || fail "ui did not open port $(service_port ui)"
wait_until 60 curl -sf "$(service_url ui)/api/revenue" || fail "ui api did not answer, see: podman logs q2-ui"
log "ui up on $(service_url ui)"

"$SCRIPTS/status.sh"

log "links"
printf "%-14s %s\n" postgres "$(service_url postgres)"
printf "%-14s %s\n" ui "$(service_url ui)"
printf "%-14s %s\n" api "$(service_url ui)/api/revenue"
