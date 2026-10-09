#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require podman-compose

if [ -f "$RUN/server.pid" ]; then
  kill "$(cat "$RUN/server.pid")" 2>/dev/null || true
  rm -f "$RUN/server.pid"
fi
pid="$(port_pid "$(service_port ui)")"
if [ -n "$pid" ] && ps -p "$pid" -o command= | grep -q "server.py"; then
  kill "$pid" 2>/dev/null || true
fi
wait_port_down "$(service_port ui)" 30 || fail "ui port $(service_port ui) still busy"

compose down >/dev/null 2>&1 || fail "podman-compose down failed"
wait_port_down "$(service_port postgres)" 30 || fail "postgres port $(service_port postgres) still busy"
log "stopped"
