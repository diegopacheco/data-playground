#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require podman-compose

log "stopping"
compose down >/dev/null 2>&1 || fail "podman-compose down failed"

for name in $(service_names); do
  port="$(service_port "$name")"
  wait_port_down "$port" 30 || fail "$name still listening on $port"
done

log "stopped (volume t4-redpanda-data kept, remove it with: podman volume rm t4-redpanda-data)"
