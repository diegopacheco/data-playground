#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require podman-compose
require curl

ensure_max_map_count

log "starting doris fe and be"
compose up -d q3-doris-fe q3-doris-be >"$LOGS/compose-up.log" 2>&1 || fail "podman-compose up failed, see $LOGS/compose-up.log"
for name in fe_http mysql be_http; do
  port="$(service_port "$name")"
  wait_port_up "$port" 60 || fail "$name did not open port $port"
done
wait_for 60 doris_sql -e "SELECT 1" || fail "doris fe does not accept mysql connections, see: podman logs q3-doris-fe"
wait_for 60 be_alive || fail "doris be is not alive, see: podman logs q3-doris-be"
log "doris up on $(service_url mysql)"

"$SCRIPTS/pipeline.sh"

log "starting ui"
compose up -d q3-ui >>"$LOGS/compose-up.log" 2>&1 || fail "podman-compose up ui failed, see $LOGS/compose-up.log"
wait_port_up "$(service_port ui)" 60 || fail "ui did not open port $(service_port ui)"
wait_for 60 curl -sf "$(service_url ui)/api/revenue" || fail "ui api did not answer, see: podman logs q3-ui"
log "ui up on $(service_url ui)"

"$SCRIPTS/status.sh"

log "links"
printf "%-14s %s\n" fe_http "$(service_url fe_http)"
printf "%-14s %s\n" mysql "$(service_url mysql)"
printf "%-14s %s\n" stream_load "$(service_url be_http)/api/sales/orders/_stream_load"
printf "%-14s %s\n" ui "$(service_url ui)"
printf "%-14s %s\n" api "$(service_url ui)/api/revenue"
