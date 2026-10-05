#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

podman-compose -f "$ROOT/podman-compose.yml" down >"$LOGS/compose-down.log" 2>&1 || fail "podman-compose down failed, see $LOGS/compose-down.log"

for name in $(service_names); do
  wait_cmd 30 port_down "$(service_port "$name")" || fail "port $(service_port "$name") for $name is still in use"
done
log "stopped"
