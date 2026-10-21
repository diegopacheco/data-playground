#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

log "starting"

require podman-compose
require curl
mkdir -p "$RESULTS_DIR"
podman-compose up -d >"$LOGS/start.log" 2>&1 || fail "podman-compose up failed, see $LOGS/start.log"

port="$(service_port ui)"
wait_port_up "$port" 60 || fail "ui did not open port $port"
wait_for 60 curl -sf "$(service_url ui)/" || fail "ui is not answering on $(service_url ui)"
log "ui up on $(service_url ui)"

"$SCRIPTS/status.sh"

log "links"
for name in $(service_names); do
  printf "%-8s %s\n" "$name" "$(service_url "$name")"
done
printf "%-8s %s\n" "api" "$(service_url ui)/api/results"
