#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

cluster_exists || fail "cluster $CLUSTER missing, run scripts/setup.sh first"
deploy_ready default kuberay-operator || fail "kuberay operator not ready, run scripts/setup.sh first"

k apply -f "$ROOT/k8s/minio.yaml" >/dev/null || fail "minio apply failed"
log "waiting for minio"
wait_long 3 deploy_ready default minio || fail "minio not ready"

k apply -f "$ROOT/k8s/raycluster.yaml" >/dev/null || fail "raycluster apply failed"
log "waiting for ray cluster etl"
wait_long 5 ray_cluster_ready || fail "ray cluster not ready, state=$(ray_cluster_state)"

if [ -n "$(k get rayjob etl-driver -o name --ignore-not-found)" ]; then
  log "rayjob etl-driver already submitted"
else
  k apply -f "$ROOT/k8s/rayjob.yaml" >/dev/null || fail "rayjob apply failed"
fi
log "waiting for rayjob etl-driver"
wait_long 3 ray_job_running || fail "rayjob not running, status=$(ray_job_status)"

k apply -f "$ROOT/k8s/producer.yaml" >/dev/null || fail "producer apply failed"
wait_long 3 deploy_ready default producer || fail "producer not ready"

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
