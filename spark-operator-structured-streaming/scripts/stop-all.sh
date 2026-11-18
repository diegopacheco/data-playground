#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

spark_pods_gone() {
  [ -z "$(k get pods -l sparkoperator.k8s.io/launched-by-spark-operator=true --no-headers 2>/dev/null)" ]
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
  log "deleting spark applications, producer, lake-query, kafka and storage"
  for app in $APPS; do
    k delete sparkapplication "$app" --ignore-not-found --wait=true --timeout=120s >/dev/null || fail "delete $app failed"
  done
  wait_until 60 spark_pods_gone || fail "spark pods still running"
  k delete -f "$ROOT/k8s/producer.yaml" -f "$ROOT/k8s/lake-query.yaml" --ignore-not-found --wait=true --timeout=60s >/dev/null || fail "producer delete failed"
  k delete -f "$ROOT/k8s/kafka.yaml" -f "$ROOT/k8s/storage.yaml" --ignore-not-found --wait=true --timeout=120s >/dev/null || fail "storage delete failed"
  k delete pvc -l app=kafka --ignore-not-found --wait=true --timeout=60s >/dev/null || fail "kafka pvc delete failed"
fi
log "stopped"
