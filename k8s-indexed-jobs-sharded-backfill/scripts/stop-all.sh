#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

backfill_pods_gone() {
  [ -z "$(k get pods -l app=backfill --no-headers 2>/dev/null)" ] && [ -z "$(k get pods -l app=postgres --no-headers 2>/dev/null)" ]
}

for name in $(service_names); do
  log "stopping port-forward $name"
  pid="$(forward_pid "$name")"
  [ -n "$pid" ] && kill "$pid" 2>/dev/null || true
  rm -f "$RUN/$name.pid"
  wait_port_down "$(service_port "$name")" || fail "port $(service_port "$name") still in use"
done

if cluster_exists; then
  log "deleting backfill jobs and postgres"
  k delete jobs -l app=backfill --ignore-not-found --wait=false >/dev/null || fail "job delete failed"
  k delete -f "$ROOT/k8s/postgres.yaml" --ignore-not-found --wait=false >/dev/null || fail "postgres delete failed"
  wait_until 60 backfill_pods_gone || fail "pods still running"
fi
log "stopped"
