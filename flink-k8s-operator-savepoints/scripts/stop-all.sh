#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

flink_pods_gone() {
  [ -z "$(k get pods -l type=flink-native-kubernetes --no-headers 2>/dev/null)" ]
}

for name in $(service_names); do
  log "stopping port-forward $name"
  pid="$(pidfile_pid "$name")"
  if [ -n "$pid" ]; then
    pkill -P "$pid" 2>/dev/null || true
    kill "$pid" 2>/dev/null || true
    pkill -P "$pid" 2>/dev/null || true
  fi
  rm -f "$RUN/$name.pid"
  forward="$(port_pid "$(service_port "$name")")"
  if [ -n "$forward" ] && ps -p "$forward" -o command= | grep "port-forward" >/dev/null; then kill "$forward" 2>/dev/null || true; fi
  wait_port_down "$(service_port "$name")" || fail "port $(service_port "$name") still in use"
done

if cluster_exists; then
  log "deleting flink deployments and state volume"
  for job in $JOBS; do
    k delete flinkdeployment "$job" --ignore-not-found --wait=true --timeout=120s >/dev/null || fail "delete $job failed"
  done
  wait_until 60 flink_pods_gone || fail "flink pods still running"
  k delete -f "$ROOT/k8s/flink-state-pvc.yaml" --ignore-not-found --wait=true --timeout=60s >/dev/null || fail "pvc delete failed"
fi
log "stopped"
