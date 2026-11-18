#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

if cluster_exists; then
  if deploy_ready spark-operator spark-operator-controller; then op="READY"; else op="ABSENT"; fi
  log "cluster $CLUSTER UP, spark operator $op"
  for d in minio postgres producer lake-query; do
    if deploy_ready default "$d"; then log "$d READY"; else log "$d ABSENT"; fi
  done
  if kafka_ready; then log "kafka READY"; else log "kafka ABSENT"; fi
  for app in $APPS; do
    state="$(app_state "$app")"
    detail="$(k get sparkapplication "$app" -o jsonpath='attempts={.status.executionAttempts} args={.spec.arguments}' 2>/dev/null || true)"
    log "$app ${state:-ABSENT} $detail"
  done
else
  log "cluster $CLUSTER DOWN"
fi

for name in $(service_names); do
  port="$(service_port "$name")"
  if port_up "$port"; then
    log "$name $port UP pid=$(port_pid "$port") $(service_url "$name")"
  else
    log "$name $port DOWN"
  fi
done
