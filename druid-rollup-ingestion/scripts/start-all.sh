#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require podman-compose
require curl
require python3

OVERLORD="$(service_url overlord)/druid/indexer/v1"

broker_ready() {
  [ "$(druid_value "SELECT 1")" = "1" ]
}

datasource_loaded() {
  local published available
  published="$(druid_value "SELECT COUNT(*) FROM sys.segments WHERE datasource='$1' AND is_published=1 AND is_overshadowed=0")"
  available="$(druid_value "SELECT COUNT(*) FROM sys.segments WHERE datasource='$1' AND is_published=1 AND is_overshadowed=0 AND is_available=1")"
  [ "${published:-0}" -gt 0 ] && [ "$published" = "$available" ]
}

task_state() {
  curl -sf "$OVERLORD/task/$1/status" | python3 -c 'import json,sys; print(json.load(sys.stdin)["status"]["statusCode"])'
}

task_done() {
  case "$(task_state "$1")" in
    SUCCESS|FAILED) return 0 ;;
    *) return 1 ;;
  esac
}

ingest() {
  local spec datasource response task
  spec="$1"
  datasource="$(basename "$spec" .json)"
  if datasource_loaded "$datasource"; then
    log "$datasource already ingested"
    return 0
  fi
  log "submitting native batch ingestion for $datasource"
  response="$(curl -sf -X POST -H 'Content-Type: application/json' --data @"$spec" "$OVERLORD/task")" || fail "task submit for $datasource failed"
  task="$(printf "%s" "$response" | python3 -c 'import json,sys; print(json.load(sys.stdin)["task"])')"
  log "task $task"
  wait_until 60 task_done "$task" || fail "task $task did not finish in 60s"
  [ "$(task_state "$task")" = "SUCCESS" ] || fail "task $task failed, see: podman exec i32-druid cat var/druid/indexing-logs/$task.log"
  wait_until 60 datasource_loaded "$datasource" || fail "segments of $datasource not loaded in 60s"
  log "$datasource ingested and loaded"
}

log "starting druid nano topology (zookeeper, coordinator-overlord, broker, historical, middleManager)"
compose up -d i32-druid >/dev/null 2>&1 || fail "could not start i32-druid"
wait_until 60 curl -sf "$(service_url broker)/status/health" || fail "broker not healthy, see: podman exec i32-druid cat log/broker.log"
wait_until 60 curl -sf "$OVERLORD/leader" || fail "overlord has no leader, see: podman exec i32-druid cat log/coordinator-overlord.log"
wait_until 60 broker_ready || fail "broker SQL not ready"
log "druid up"

ingest "$ROOT/ingestion/orders_rollup.json"
ingest "$ROOT/ingestion/orders_raw.json"

log "starting ui"
compose up -d --no-deps i32-ui >/dev/null 2>&1 || fail "could not start i32-ui"
wait_until 60 curl -sf "$(service_url ui)/api/summary" || fail "ui api did not answer, see: podman logs i32-ui"

"$SCRIPTS/status.sh"

log "links"
printf "%-10s %s\n" broker-sql "$(service_url broker)/druid/v2/sql"
printf "%-10s %s\n" overlord "$(service_url overlord)/druid/indexer/v1"
printf "%-10s %s\n" ui "$(service_url ui)"
printf "%-10s %s\n" api "$(service_url ui)/api/summary"
