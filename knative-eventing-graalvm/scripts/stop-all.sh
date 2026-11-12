#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

pods_gone() {
  [ -z "$(k get pods -l 'app in (orders,lab,kafka)' --no-headers 2>/dev/null)" ]
}

for name in $(service_names); do
  log "stopping port-forward $name"
  pid="$(forward_pid "$name")"
  [ -n "$pid" ] && kill "$pid" 2>/dev/null || true
  rm -f "$RUN/$name.pid"
  wait_port_down "$(service_port "$name")" || fail "port $(service_port "$name") still in use"
done

if cluster_exists; then
  log "deleting kafka sources, knative services, lab and kafka (the kafka PVC is kept)"
  for file in sources services lab kafka; do
    k delete -f "$ROOT/k8s/$file.yaml" --ignore-not-found --wait=false >/dev/null || fail "$file delete failed"
  done
  wait_long pods_gone || fail "pods still running"
fi
log "stopped"
