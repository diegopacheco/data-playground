#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

pipeline_pods_gone() {
  [ -z "$(k get pods -l "numaflow.numaproj.io/pipeline-name=$PIPELINE" --no-headers 2>/dev/null | awk '$3!="Completed"')" ]
}

for name in $(service_names); do
  log "stopping port-forward $name"
  pid="$(forward_pid "$name")"
  [ -n "$pid" ] && kill "$pid" 2>/dev/null || true
  rm -f "$RUN/$name.pid"
  wait_port_down "$(service_port "$name")" || fail "port $(service_port "$name") still in use"
done

if cluster_exists; then
  log "deleting pipeline $PIPELINE"
  k delete -f "$ROOT/k8s/pipeline.yaml" --ignore-not-found --wait=false >/dev/null || fail "pipeline delete failed"
  log "waiting for pipeline pods to terminate"
  wait_until 60 pipeline_pods_gone || fail "pipeline pods still running"
fi

if [ "${1:-}" = "--cluster" ] && cluster_exists; then
  kind delete cluster --name "$CLUSTER" || fail "kind delete cluster failed"
fi
log "stopped"
