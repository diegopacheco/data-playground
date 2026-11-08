#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

pods_gone() {
  [ -z "$(k get pods -l 'app in (bench,iggy,kafka)' --no-headers 2>/dev/null)" ]
}

for name in $(service_names); do
  log "stopping port-forward $name"
  pid="$(forward_pid "$name")"
  [ -n "$pid" ] && kill "$pid" 2>/dev/null || true
  rm -f "$RUN/$name.pid"
  wait_port_down "$(service_port "$name")" || fail "port $(service_port "$name") still in use"
done

if cluster_exists; then
  log "deleting bench jobs, iggy and kafka (PVCs are kept)"
  k delete jobs -l app=bench --ignore-not-found --wait=false >/dev/null || fail "job delete failed"
  for broker in iggy kafka; do
    k delete -f "$ROOT/k8s/$broker.yaml" --ignore-not-found --wait=false >/dev/null || fail "$broker delete failed"
  done
  wait_until 60 pods_gone || wait_until 60 pods_gone || fail "pods still running"
fi
log "stopped"
