#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require podman-compose
require curl

log "starting redpanda, arroyo and ui"
compose up -d >"$LOGS/compose-up.log" 2>&1 || fail "podman-compose up failed, see $LOGS/compose-up.log"

for name in $(service_names); do
  port="$(service_port "$name")"
  wait_port_up "$port" 60 || fail "$name did not open port $port"
done

wait_until 60 redpanda_ready || fail "redpanda is not healthy, see: podman logs $REDPANDA_CONTAINER"
log "redpanda up on $(service_url redpanda)"

wait_until 60 arroyo_ready || fail "arroyo api did not answer, see: podman logs q1-arroyo"
log "arroyo up on $(service_url arroyo)"

wait_until 60 curl -sf "$(service_url ui)/" || fail "ui did not answer, see: podman logs q1-ui"
log "ui up on $(service_url ui)"

"$SCRIPTS/status.sh"

log "links"
for name in $(service_names); do
  printf "%-14s %s\n" "$name" "$(service_url "$name")"
done
printf "%-14s %s\n" "arroyo-api" "$(service_url arroyo)/api/v1/pipelines"
printf "%-14s %s\n" "api" "$(service_url ui)/api/revenue"
