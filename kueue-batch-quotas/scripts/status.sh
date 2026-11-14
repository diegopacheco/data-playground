#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

if cluster_exists; then
  if kueue_ready; then kueue="READY"; else kueue="ABSENT"; fi
  if deployment_ready kueue-kueueviz-frontend; then viz="READY"; else viz="ABSENT"; fi
  cqs="$(k get clusterqueues --no-headers 2>/dev/null | wc -l | tr -d ' ')"
  wls="$(k get workloads -A --no-headers 2>/dev/null | wc -l | tr -d ' ')"
  log "cluster $CLUSTER UP, kueue $KUEUE_VERSION $kueue, kueueviz $viz, cluster queues $cqs, workloads $wls"
  if [ "$cqs" != "0" ]; then
    k get clusterqueues -o custom-columns='QUEUE:.metadata.name,COHORT:.spec.cohortName,STRATEGY:.spec.queueingStrategy,PENDING:.status.pendingWorkloads,ADMITTED:.status.admittedWorkloads'
  fi
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
