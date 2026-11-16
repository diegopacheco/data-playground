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

log "stopped (volumes t5-redpanda-data, t5-postgres-data and t5-connect-out kept, remove them with: podman volume rm t5-redpanda-data t5-postgres-data t5-connect-out)"
