#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

log "stopping ui"
if [ -f "$RUN/ui.pid" ]; then
  kill "$(cat "$RUN/ui.pid")" 2>/dev/null || true
  rm -f "$RUN/ui.pid"
fi
pid="$(port_pid "$(service_port ui)")"
[ -z "$pid" ] || kill "$pid" 2>/dev/null || true

for name in $(service_names); do
  port="$(service_port "$name")"
  wait_port_down "$port" 30 || fail "$name still listening on $port"
done

log "stopped"
