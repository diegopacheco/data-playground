#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

workload_pods_gone() {
  [ -z "$(k get pods -l 'app in (generator,java-loader,python-loader)' --no-headers 2>/dev/null)" ]
}

for name in $(service_names); do
  log "stopping port-forward $name"
  pid="$(forward_pid "$name")"
  [ -n "$pid" ] && kill "$pid" 2>/dev/null || true
  rm -f "$RUN/$name.pid"
  wait_port_down "$(service_port "$name")" || fail "port $(service_port "$name") still in use"
done

if cluster_exists; then
  log "deleting generator, cronjobs and their jobs"
  k delete -f "$ROOT/k8s/generator.yaml" -f "$ROOT/k8s/cronjobs.yaml" --ignore-not-found --wait=false >/dev/null || fail "delete failed"
  k delete jobs --all --ignore-not-found >/dev/null || fail "job delete failed"
  wait_until 60 workload_pods_gone || fail "workload pods still running"
fi
log "stopped, postgres keeps its data, scripts/teardown.sh deletes everything"
