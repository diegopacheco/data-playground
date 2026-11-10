#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

cluster_exists || fail "cluster $CLUSTER missing, run scripts/setup.sh first"
deploy_ready default flink-kubernetes-operator || fail "operator not ready, run scripts/setup.sh first"

k apply -f "$ROOT/k8s/flink-state-pvc.yaml" >/dev/null || fail "pvc apply failed"
for job in $JOBS; do
  if [ -n "$(k get flinkdeployment "$job" -o name --ignore-not-found)" ]; then
    log "$job already deployed"
  else
    k apply -f "$ROOT/k8s/$job.yaml" >/dev/null || fail "$job apply failed"
  fi
done
for job in $JOBS; do
  log "waiting for $job to be RUNNING"
  wait_long 5 job_running "$job" || fail "$job not running, state=$(job_state "$job")"
done

for name in $(service_names); do
  port="$(service_port "$name")"
  if port_up "$port"; then
    log "$name already forwarded on $port"
    continue
  fi
  target="$(service_target "$name")"
  nohup bash -c "while true; do kubectl --context '$CTX' port-forward ${target% *} '$port:${target##* }'; sleep 1; done" > "$RUN/logs/$name.log" 2>&1 &
  echo "$!" > "$RUN/$name.pid"
  wait_until 60 port_up "$port" || fail "port-forward for $name did not open $port, see $RUN/logs/$name.log"
done

for name in $(service_names); do
  log "$name: $(service_url "$name")"
done
