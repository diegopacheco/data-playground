#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

etl_pods_gone() {
  [ -z "$(k get pods -A -l app=etl --no-headers 2>/dev/null)" ]
}

for name in $(service_names); do
  log "stopping port-forward $name"
  pid="$(forward_pid "$name")"
  [ -n "$pid" ] && kill "$pid" 2>/dev/null || true
  rm -f "$RUN/$name.pid"
  wait_port_down "$(service_port "$name")" || fail "port $(service_port "$name") still in use"
done

if cluster_exists; then
  log "deleting etl jobs, queues, team namespaces and kueueviz (kueue itself stays installed)"
  for ns in team-analytics team-finance team-reports; do
    k -n "$ns" delete jobs -l app=etl --ignore-not-found --wait=false >/dev/null 2>&1 || true
  done
  wait_until 60 etl_pods_gone || fail "etl pods still running"
  k delete -f "$ROOT/k8s/queues.yaml" --ignore-not-found --timeout=60s >/dev/null || fail "queues delete failed"
  if [ -s "$VENDOR/$KUEUE_VERSION-kueueviz-single-host.yaml" ]; then
    k delete -f "$VENDOR/$KUEUE_VERSION-kueueviz-single-host.yaml" --ignore-not-found --timeout=60s >/dev/null || fail "kueueviz delete failed"
  fi
fi
log "stopped"
