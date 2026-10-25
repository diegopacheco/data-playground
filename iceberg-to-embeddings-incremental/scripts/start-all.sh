#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require podman-compose
require curl
[ -x "$PY" ] || fail "venv missing, run scripts/setup.sh first"
mkdir -p "$RUN/logs"

log "starting minio and postgres with pgvector"
compose up -d s8-minio s8-postgres >/dev/null 2>&1 || fail "podman-compose up failed"
wait_until 60 podman exec s8-postgres pg_isready -U s8 -d vectors || fail "postgres not ready, see: podman logs s8-postgres"
wait_until 60 curl -sf "$(service_url minio)/minio/health/ready" || fail "minio not ready, see: podman logs s8-minio"
wait_until 60 mc alias set local http://localhost:9000 s8admin s8password || fail "mc alias failed"

if ! port_up "$(service_port ui)"; then
  log "starting a fresh iceberg rest catalog"
  compose up -d --force-recreate --no-deps s8-rest >/dev/null 2>&1 || fail "rest catalog start failed"
  wait_until 60 curl -sf "$(service_url rest)/v1/config" || fail "rest catalog not ready, see: podman logs s8-rest"
  log "resetting bucket warehouse in minio and the vector store in postgres"
  mc rb --force local/warehouse >/dev/null 2>&1 || true
  mc mb local/warehouse >/dev/null || fail "could not create bucket warehouse"
  wait_until 60 psql_exec -q -c "SELECT 1" || fail "postgres does not accept queries"
  psql_exec -q -c "SET client_min_messages = warning; DROP TABLE IF EXISTS documents, sync_state, sync_rounds;" >/dev/null || fail "vector store reset failed"
  log "running five rounds of table change followed by incremental sync"
  "$PY" "$ROOT/app/pipeline.py" 2>"$RUN/logs/pipeline.log" || fail "pipeline failed, see .run/logs/pipeline.log"
  log "starting ui"
  nohup "$PY" "$ROOT/app/server.py" >"$RUN/logs/ui.log" 2>&1 &
  echo $! >"$RUN/ui.pid"
  wait_until 60 curl -sf "$(service_url ui)/api/rounds" || fail "ui did not answer, see .run/logs/ui.log"
fi

"$SCRIPTS/status.sh" || fail "a service is down"

log "links"
printf "%-14s %s\n" minio-s3 "$(service_url minio)"
printf "%-14s %s\n" minio-console "$(service_url console)"
printf "%-14s %s\n" rest-catalog "$(service_url rest)/v1/config"
printf "%-14s %s\n" postgres "$(service_url postgres)"
printf "%-14s %s\n" ui "$(service_url ui)"
printf "%-14s %s\n" api "$(service_url ui)/api/rounds"
