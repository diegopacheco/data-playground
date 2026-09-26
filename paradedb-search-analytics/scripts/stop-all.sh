#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require podman-compose

compose down >"$LOGS/compose-down.log" 2>&1 || fail "podman-compose down failed, see .run/logs/compose-down.log"
for name in $(service_names); do
  wait_port_down "$(service_port "$name")" 30 || fail "$name port $(service_port "$name") still busy"
done
log "stopped"
