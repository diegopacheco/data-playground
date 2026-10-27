#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require podman-compose
require curl
[ -x "$PY" ] || fail "venv missing, run scripts/setup.sh first"
mkdir -p "$RUN/logs"

if ! port_up "$(service_port ui)"; then
  log "starting a fresh minio with bucket s1-lake"
  compose down -v >/dev/null 2>&1 || true
  compose up -d s1-minio >/dev/null 2>&1 || fail "podman-compose up s1-minio failed"
  wait_until 60 curl -sf "$(service_url minio)/minio/health/ready" || fail "minio not ready, see: podman logs s1-minio"
  wait_until 60 mc alias set local http://localhost:9000 s1admin s1password || fail "mc alias failed"
  mc mb local/s1-lake >/dev/null || fail "could not create bucket s1-lake"

  log "starting iceberg rest catalog and redpanda with iceberg enabled"
  compose up -d >/dev/null 2>&1 || fail "podman-compose up failed"
  wait_until 60 curl -sf "$(service_url rest)/v1/config" || fail "iceberg rest catalog not ready, see: podman logs s1-rest"
  wait_until 60 curl -sf "$(service_url admin)/v1/status/ready" || fail "redpanda not ready, see: podman logs s1-redpanda"
  wait_until 60 curl -sf "$(service_url registry)/subjects" || fail "schema registry not ready, see: podman logs s1-redpanda"
  wait_until 60 curl -sf "$(service_url proxy)/topics" || fail "http proxy not ready, see: podman logs s1-redpanda"
  [ "$(rpk cluster config get iceberg_enabled)" = "true" ] || fail "iceberg_enabled is not true, bootstrap config was not applied"

  log "creating topics with redpanda.iceberg.mode"
  rpk topic create orders_kv -p 1 -c redpanda.iceberg.mode=key_value >/dev/null || fail "could not create topic orders_kv"
  rpk topic create orders_typed -p 1 -c redpanda.iceberg.mode=value_schema_id_prefix >/dev/null || fail "could not create topic orders_typed"

  log "producing orders and waiting for each batch to be readable from iceberg"
  "$PY" "$ROOT/app/pipeline.py" || fail "pipeline failed"

  log "starting ui"
  nohup "$PY" "$ROOT/app/server.py" >"$RUN/logs/ui.log" 2>&1 &
  echo $! >"$RUN/ui.pid"
  wait_until 60 curl -sf "$(service_url ui)/api/tables" || fail "ui did not answer, see .run/logs/ui.log"
fi

"$SCRIPTS/status.sh" || fail "a service is down"

log "links"
printf "%-16s %s\n" kafka "$(service_url kafka)"
printf "%-16s %s\n" http-proxy "$(service_url proxy)/topics"
printf "%-16s %s\n" schema-registry "$(service_url registry)/subjects"
printf "%-16s %s\n" redpanda-admin "$(service_url admin)/v1/features/license"
printf "%-16s %s\n" minio-s3 "$(service_url minio)"
printf "%-16s %s\n" minio-console "$(service_url console)"
printf "%-16s %s\n" iceberg-rest "$(service_url rest)/v1/namespaces/redpanda/tables"
printf "%-16s %s\n" ui "$(service_url ui)"
printf "%-16s %s\n" api "$(service_url ui)/api/tables"
