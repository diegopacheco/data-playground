#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

log "stopping"

stop_bg ui

if [ -f "$ROOT/project/target/active.json" ] && command -v sbt >/dev/null 2>&1; then
  sbt shutdown >"$LOGS/sbt-shutdown.log" 2>&1 || true
  rm -f "$ROOT/project/target/active.json"
fi

require podman-compose
podman-compose down

for name in $(service_names); do
  port="$(service_port "$name")"
  wait_port_down "$port" 30 || fail "$name still listening on $port"
done

log "stopped"
