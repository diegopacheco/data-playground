#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

log "starting"

require podman-compose
require curl
[ -x "$VENV/bin/python" ] || fail "client venv missing, run ./scripts/setup.sh first"

podman-compose up -d
wait_http "http://localhost:$HTTP_PORT/health" 60 || fail "flight server not ready, see podman logs i13-flight-server"
wait_port_up "$FLIGHT_PORT" 60 || fail "flight did not open port $FLIGHT_PORT"
log "flight up on $(service_url flight)"

start_bg ui "$ROOT/client" "$VENV/bin/python" app.py
wait_port_up "$UI_PORT" 60 || fail "ui did not open port $UI_PORT, see $LOGS/ui.log"
log "ui up on $(service_url ui)"

"$SCRIPTS/status.sh"

log "links"
for name in $(service_names); do
  printf "%-10s %s\n" "$name" "$(service_url "$name")"
done
