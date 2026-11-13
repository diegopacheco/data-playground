#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

if cluster_exists; then
  if deploy_ready default kuberay-operator; then op="READY"; else op="NOT READY"; fi
  if deploy_ready default minio; then minio="READY"; else minio="NOT READY"; fi
  if deploy_ready default producer; then producer="READY"; else producer="NOT READY"; fi
  log "cluster $CLUSTER UP, kuberay operator $op, minio $minio, producer $producer"
  state="$(ray_cluster_state)"
  workers="$(k get raycluster etl -o jsonpath='{.status.availableWorkerReplicas}/{.status.desiredWorkerReplicas} workers (min {.status.minWorkerReplicas}, max {.status.maxWorkerReplicas})' 2>/dev/null || true)"
  log "raycluster etl ${state:-ABSENT} $workers"
  job="$(ray_job_status)"
  log "rayjob etl-driver ${job:-ABSENT}"
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
