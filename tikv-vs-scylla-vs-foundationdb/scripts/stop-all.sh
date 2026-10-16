#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require podman-compose

log "stopping ui"
podman rm -f s6-ui s6-bench >/dev/null 2>&1 || true

log "stopping pd, tikv, scylladb and foundationdb"
compose down >"$LOGS/compose.log" 2>&1 || fail "podman-compose down failed, see .run/logs/compose.log"

for name in $(service_names); do
  port="$(service_port "$name")"
  wait_port_down "$port" 30 || fail "$name still listening on $port"
done

log "stopped"
