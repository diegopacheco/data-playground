#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require podman-compose
[ -f "$ROOT/comparison.json" ] || fail "comparison.json is missing, run ./scripts/setup.sh first"

log "starting"
if ! port_up "$(service_port ui)"; then
  compose up -d >"$LOGS/compose-up.log" 2>&1 || fail "podman-compose up failed, see $LOGS/compose-up.log"
fi
wait_http "$(service_url ui)/api/health" 60 || fail "ui did not answer on $(service_url ui)"
log "ui up on $(service_url ui)"

"$SCRIPTS/status.sh"

log "links"
printf "%-14s %s\n" ui "$(service_url ui)"
printf "%-14s %s\n" api "$(service_url ui)/api/comparison"
