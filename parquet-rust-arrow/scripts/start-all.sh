#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

log "starting"

[ -x "$BIN" ] || build_app
start_bg ui env PORT="$(service_port ui)" "$BIN" serve
wait_port_up "$(service_port ui)" 60 || fail "ui did not open port $(service_port ui), see $LOGS/ui.log"
log "ui up on $(service_url ui)"

"$SCRIPTS/status.sh"

log "links"
printf "%-14s %s\n" "ui" "$(service_url ui)"
printf "%-14s %s\n" "aggregates" "$(service_url ui)/api/aggregates?from=2026-01-12"
printf "%-14s %s\n" "metadata" "$(service_url ui)/api/metadata"
