#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require podman-compose
require curl
[ -x "$PY" ] || fail "run scripts/setup.sh first"
[ -f "$ROOT/data/customers.csv" ] || fail "run scripts/setup.sh first"
mkdir -p "$RUN/logs"

log "starting postgres and opa"
compose up -d s5-postgres s5-opa >/dev/null 2>&1 || fail "podman-compose up failed for postgres and opa"
wait_until 60 postgres_ready || fail "postgres not ready, see: podman logs s5-postgres"
wait_until 60 opa_ready || fail "opa not ready, see: podman logs s5-opa"

log "loading customers and orders into postgres"
psql_exec -f /sql/postgres.sql || fail "could not load postgres"

log "starting trino"
compose up -d s5-trino >/dev/null 2>&1 || fail "podman-compose up failed for trino"
wait_until 60 trino_ready || wait_until 60 trino_ready || fail "trino not ready, see: podman logs s5-trino"

log "pushing policy files to opa"
"$SCRIPTS/reload-policy.sh" >/dev/null

log "creating views and copies in the scratch catalog"
TRINO_URL="$(service_url trino)" "$PY" "$ROOT/app/bootstrap.py" || fail "bootstrap failed"

if ! port_up "$(service_port ui)"; then
  log "starting ui"
  UI_PORT="$(service_port ui)" TRINO_URL="$(service_url trino)" OPA_URL="$(service_url opa)" \
    nohup "$PY" "$ROOT/app/server.py" >"$RUN/logs/ui.log" 2>&1 &
  echo $! >"$RUN/ui.pid"
fi
wait_until 60 ui_ready || fail "ui not ready, see .run/logs/ui.log"

"$SCRIPTS/status.sh"

log "links"
printf "%-10s %s\n" postgres "$(service_url postgres)"
printf "%-10s %s\n" opa "$(service_url opa)/v1/data/pii"
printf "%-10s %s\n" trino "$(service_url trino)/ui/"
printf "%-10s %s\n" ui "$(service_url ui)"
printf "%-10s %s\n" api "$(service_url ui)/api/compare?case=columns"
