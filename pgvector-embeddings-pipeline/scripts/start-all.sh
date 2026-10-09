#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require podman-compose
require curl
[ -x "$PY" ] || fail "venv missing, run scripts/setup.sh first"
mkdir -p "$RUN/logs"

log "starting postgres with pgvector"
compose up -d >/dev/null 2>&1 || fail "podman-compose up failed"
wait_until 60 podman exec i48-postgres pg_isready -U catalog -d catalog || fail "postgres not ready, see: podman logs i48-postgres"
wait_until 30 psql_exec -tAc "select 1" || fail "postgres not accepting queries"
log "postgres up on $(service_url postgres)"

done_rows="$(psql_exec -tAc "select count(*) from pg_tables where tablename = 'pipeline_results'")"
if [ "$done_rows" = "0" ] || [ "$(psql_exec -tAc "select count(*) from pipeline_results")" = "0" ]; then
  log "running embeddings pipeline"
  run_py pipeline.py 2>"$RUN/logs/pipeline.err" </dev/null | tee "$RUN/logs/pipeline.log" || fail "pipeline failed, see .run/logs/pipeline.err"
else
  log "pipeline already ran, skipping"
fi

if ! port_up "$(service_port ui)"; then
  log "starting search api and ui"
  PGPORT="$(service_port postgres)" UI_PORT="$(service_port ui)" nohup "$PY" "$ROOT/app/server.py" >"$RUN/logs/server.log" 2>&1 </dev/null &
  echo $! >"$RUN/server.pid"
  wait_until 60 curl -sf "$(service_url ui)/api/pipeline" || fail "ui did not answer, see .run/logs/server.log"
fi
log "ui up on $(service_url ui)"

"$SCRIPTS/status.sh"

log "links"
printf "%-10s %s\n" postgres "$(service_url postgres)"
printf "%-10s %s\n" ui "$(service_url ui)"
printf "%-10s %s\n" search "$(service_url ui)/api/search?q=something+to+read"
printf "%-10s %s\n" pipeline "$(service_url ui)/api/pipeline"
