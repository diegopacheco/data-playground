#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

if cluster_exists; then
  if deploy_ready default flink-kubernetes-operator; then op="READY"; else op="ABSENT"; fi
  log "cluster $CLUSTER UP, flink operator $op"
  for job in $JOBS; do
    state="$(job_state "$job")"
    mode="$(k get flinkdeployment "$job" -o jsonpath='{.spec.job.upgradeMode} parallelism={.spec.job.parallelism}' 2>/dev/null || true)"
    log "$job ${state:-ABSENT} $mode"
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
