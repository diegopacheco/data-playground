#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

airflow_cli() {
  podman exec "$AIRFLOW_CONTAINER" airflow "$@" 2>/dev/null
}

dag_loaded() {
  airflow_cli dags list -o plain | awk -v d="$DAG_ID" '$1==d{f=1} END{exit !f}'
}

run_state() {
  airflow_cli dags list-runs "$DAG_ID" -o plain | awk -v id="$1" '$2==id{print $3}'
}

wait_cmd 60 dag_loaded || fail "dag $DAG_ID was not loaded by airflow"

run_id="run_$(date +%Y%m%dT%H%M%S)"
airflow_cli dags trigger "$DAG_ID" -r "$run_id" >/dev/null || fail "trigger of $DAG_ID failed"
log "triggered $DAG_ID run $run_id"

tries=60
while [ "$tries" -gt 0 ]; do
  state="$(run_state "$run_id")"
  case "$state" in
    success) log "run $run_id success"; exit 0 ;;
    failed) fail "run $run_id failed, see $(service_url airflow)" ;;
  esac
  sleep 1
  tries=$((tries - 1))
done
fail "run $run_id did not finish in time, last state ${state:-unknown}"
