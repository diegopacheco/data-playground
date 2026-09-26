#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require podman-compose
require node
require npm
[ -d "$ROOT/node_modules" ] || fail "dependencies missing, run ./scripts/setup.sh first"

log "starting"
mkdir -p "$ROOT/tmp/pgdata"
if ! port_up "$(service_port postgres)"; then
  compose up -d >"$LOGS/postgres.log" 2>&1 || fail "postgres did not start, see $LOGS/postgres.log"
fi
wait_port_up "$(service_port postgres)" 60 || fail "postgres did not open port $(service_port postgres)"
log "postgres up on $(service_url postgres)"

start_bg backend "$ROOT" node backend/server.js
wait_port_up "$(service_port backend)" 60 || fail "backend did not open port $(service_port backend), see $LOGS/backend.log"
log "backend up on $(service_url backend)"

start_bg frontend "$ROOT" npx vite
wait_port_up "$(service_port frontend)" 60 || fail "frontend did not open port $(service_port frontend), see $LOGS/frontend.log"
log "frontend up on $(service_url frontend)"

case "$(seed_status)" in
  *'"phase":"ready"'*) log "database ready" ;;
  *) log "database is seeding the 5M row dataset in the background, progress: $(service_url backend)" ;;
esac

"$SCRIPTS/status.sh"

log "links"
for name in $(service_names); do
  printf "%-14s %s\n" "$name" "$(service_url "$name")"
done
