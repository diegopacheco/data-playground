#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

log "stopping"

stop_bg ui

if command -v podman >/dev/null 2>&1 && [ -n "$(podman ps -q --filter "name=^$CONTAINER\$" 2>/dev/null)" ]; then
  require podman-compose
  podman-compose down
fi

for name in $(service_names); do
  port="$(service_port "$name")"
  wait_port_down "$port" 10 || fail "$name still listening on $port"
done

log "stopped"
