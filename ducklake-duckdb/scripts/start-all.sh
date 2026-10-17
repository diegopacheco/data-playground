#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require podman-compose
require curl
[ -x "$PY" ] || fail "venv missing, run scripts/setup.sh first"
mkdir -p "$RUN/logs"

log "starting postgres and minio"
compose up -d >/dev/null 2>&1 || fail "podman-compose up failed"
wait_until 60 podman exec i10-postgres pg_isready -U i10 -d i10catalog || fail "postgres not ready, see: podman logs i10-postgres"
wait_until 60 curl -sf "$(service_url minio)/minio/health/ready" || fail "minio not ready, see: podman logs i10-minio"
wait_until 60 mc alias set local http://localhost:9000 i10admin i10password || fail "mc alias failed"

if ! port_up "$(service_port ui)"; then
  log "resetting ducklake catalog in postgres and bucket i10-lake in minio"
  psql_exec -q -c "SET client_min_messages = warning; DROP SCHEMA public CASCADE; CREATE SCHEMA public;" >/dev/null || fail "catalog reset failed"
  mc rb --force local/i10-lake >/dev/null 2>&1 || true
  mc mb local/i10-lake >/dev/null || fail "could not create bucket i10-lake"
  log "running ducklake pipeline with two duckdb clients"
  "$PY" "$ROOT/app/pipeline.py" || fail "pipeline failed"
  log "starting ui"
  nohup "$PY" "$ROOT/app/server.py" >"$RUN/logs/ui.log" 2>&1 &
  echo $! >"$RUN/ui.pid"
  wait_until 60 curl -sf "$(service_url ui)/api/snapshots" || fail "ui did not answer, see .run/logs/ui.log"
fi

"$SCRIPTS/status.sh" || fail "a service is down"

log "links"
printf "%-14s %s\n" postgres "$(service_url postgres)"
printf "%-14s %s\n" minio-s3 "$(service_url minio)"
printf "%-14s %s\n" minio-console "$(service_url console)"
printf "%-14s %s\n" ui "$(service_url ui)"
printf "%-14s %s\n" api "$(service_url ui)/api/snapshots"
