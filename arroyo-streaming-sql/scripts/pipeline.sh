#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require curl
require python3
port_up "$(service_port redpanda)" || fail "redpanda is not running, run ./scripts/start-all.sh first"
arroyo_ready >/dev/null || fail "arroyo is not running, run ./scripts/start-all.sh first"

pipeline_ids() {
  arroyo_api GET /pipelines | json_get "print('\n'.join(p['id'] for p in d['data'] if p['name']=='$PIPELINE_NAME'))"
}

job_state() {
  arroyo_api GET "/pipelines/$1/jobs" | json_get "print(d['data'][0]['state'] if d['data'] else 'None')"
}

job_in_state() {
  local state
  state="$(job_state "$1")"
  shift
  for wanted in "$@"; do
    if [ "$state" = "$wanted" ]; then return 0; fi
  done
  return 1
}

remove_pipeline() {
  log "stopping pipeline $1"
  arroyo_api PATCH "/pipelines/$1" -d '{"stop":"immediate"}' >/dev/null || fail "could not stop pipeline $1"
  wait_until 60 job_in_state "$1" Stopped Failed Finished None || fail "pipeline $1 did not stop"
  arroyo_api DELETE "/pipelines/$1" >/dev/null || fail "could not delete pipeline $1"
}

topic_exists() {
  podman exec "$REDPANDA_CONTAINER" rpk topic list | awk 'NR>1{print $1}' | grep -qx "$1"
}

recreate_topic() {
  if topic_exists "$1"; then
    podman exec "$REDPANDA_CONTAINER" rpk topic delete "$1" >/dev/null
  fi
  wait_until 30 podman exec "$REDPANDA_CONTAINER" rpk topic create "$1" -p 1 || fail "could not create topic $1"
}

for id in $(pipeline_ids); do
  remove_pipeline "$id"
done

recreate_topic "$SOURCE_TOPIC"
recreate_topic "$RESULT_TOPIC"
log "topics $SOURCE_TOPIC and $RESULT_TOPIC recreated"

rows="$(tail -n +2 "$ROOT/data/orders.csv" | wc -l | tr -d ' ')"
produce_orders >"$LOGS/produce.log" || fail "produce failed"
log "produced $rows orders into topic $SOURCE_TOPIC"

body="$(python3 -c 'import json,sys; print(json.dumps({"name": sys.argv[1], "query": open(sys.argv[2]).read(), "parallelism": 1}))' "$PIPELINE_NAME" "$ROOT/arroyo/revenue.sql")"
id="$(arroyo_api POST /pipelines -d "$body" | json_get "print(d['id'])")" || fail "arroyo rejected the pipeline"
log "created arroyo pipeline $id"

wait_until 60 job_in_state "$id" Running || fail "pipeline $id is not running, state $(job_state "$id")"
log "pipeline $id running, sink topic $RESULT_TOPIC"
