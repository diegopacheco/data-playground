#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

ray_pods_gone() {
  [ -z "$(k get pods -l ray.io/cluster=etl --no-headers 2>/dev/null)" ]
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
  log "deleting producer, rayjob, ray cluster and minio"
  k delete jobs -l app=producer-burst --ignore-not-found --wait=true --timeout=60s >/dev/null || fail "delete burst jobs failed"
  k delete -f "$ROOT/k8s/producer.yaml" --ignore-not-found --wait=true --timeout=60s >/dev/null || fail "delete producer failed"
  k delete -f "$ROOT/k8s/rayjob.yaml" --ignore-not-found --wait=true --timeout=120s >/dev/null || fail "delete rayjob failed"
  k delete -f "$ROOT/k8s/raycluster.yaml" --ignore-not-found --wait=true --timeout=120s >/dev/null || fail "delete raycluster failed"
  wait_long 2 ray_pods_gone || fail "ray pods still running"
  k delete -f "$ROOT/k8s/minio.yaml" --ignore-not-found --wait=true --timeout=60s >/dev/null || fail "delete minio failed"
fi
log "stopped"
