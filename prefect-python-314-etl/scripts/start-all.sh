#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

log "starting"
[ -x "$VENV/bin/prefect" ] || fail "venv missing, run ./scripts/setup.sh first"

require podman-compose
podman-compose up -d

wait_port_up "$POSTGRES_PORT" 60 || fail "postgres did not open port $POSTGRES_PORT"
tries=60
until podman exec i37-postgres pg_isready -U etl -d sales >/dev/null 2>&1; do
  tries=$((tries - 1))
  [ "$tries" -gt 0 ] || fail "postgres is not ready"
  sleep 1
done
log "postgres up on $(service_url postgres)"

tries=60
until curl -sf "$PREFECT_API_URL/health" >/dev/null 2>&1; do
  tries=$((tries - 1))
  [ "$tries" -gt 0 ] || fail "prefect server is not healthy, see podman logs i37-prefect"
  sleep 1
done
log "prefect up on $(service_url prefect)"

start_bg serve "$ROOT/etl" "$VENV/bin/python" serve.py
tries=60
until "$VENV/bin/prefect" deployment inspect "$DEPLOYMENT" >/dev/null 2>&1; do
  tries=$((tries - 1))
  [ "$tries" -gt 0 ] || fail "deployment $DEPLOYMENT not registered, see $LOGS/serve.log"
  sleep 1
done
log "deployment $DEPLOYMENT served"

start_bg ui "$ROOT/ui" "$VENV/bin/python" server.py
wait_port_up "$UI_PORT" 60 || fail "ui did not open port $UI_PORT, see $LOGS/ui.log"
log "ui up on $(service_url ui)"

"$SCRIPTS/status.sh"

log "links"
for name in $(service_names); do
  printf "%-14s %s\n" "$name" "$(service_url "$name")"
done
