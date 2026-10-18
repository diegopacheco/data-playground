#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require podman-compose

log "stopping ui and workers"
for name in ui worker; do
  if [ -f "$RUN/$name.pid" ]; then
    kill -9 "$(cat "$RUN/$name.pid")" 2>/dev/null || true
    rm -f "$RUN/$name.pid"
  fi
done
pid="$(port_pid "$(service_port ui)")"
[ -z "$pid" ] || kill "$pid" 2>/dev/null || true

log "stopping kafka"
compose down >/dev/null 2>&1 || fail "podman-compose down failed"

for name in $(service_names); do
  port="$(service_port "$name")"
  wait_port_down "$port" 30 || fail "$name still listening on $port"
done

log "stopped"
