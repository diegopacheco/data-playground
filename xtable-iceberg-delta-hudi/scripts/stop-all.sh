#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require podman-compose

podman-compose down >"$LOGS/stop.log" 2>&1 || fail "podman-compose down failed, see $LOGS/stop.log"
port="$(service_port ui)"
wait_port_down "$port" 30 || fail "port $port is still in use"
log "stopped"
