#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

app_pods_gone() {
  [ -z "$(k get pods -l 'app in (order-producer,lag-consumer)' --no-headers 2>/dev/null)" ]
}

for name in $(service_names); do
  log "stopping port-forward $name"
  pid="$(forward_pid "$name")"
  [ -n "$pid" ] && kill "$pid" 2>/dev/null || true
  rm -f "$RUN/$name.pid"
  wait_port_down "$(service_port "$name")" || fail "port $(service_port "$name") still in use"
done

if cluster_exists; then
  log "deleting producer and consumer"
  k delete -f "$ROOT/k8s/apps.yaml" --ignore-not-found --wait=false >/dev/null || fail "apps delete failed"
  wait_until 60 app_pods_gone || fail "producer or consumer pods still running"
fi
log "stopped, kafka, postgres and the observability stack keep running (scripts/teardown.sh deletes them)"
