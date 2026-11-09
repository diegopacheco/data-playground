#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

cluster_exists || fail "cluster $CLUSTER missing, run scripts/setup.sh first"
k rollout status statefulset/postgres --timeout=120s >/dev/null || fail "postgres not ready, run scripts/setup.sh"

k apply -f "$ROOT/k8s/generator.yaml" -f "$ROOT/k8s/cronjobs.yaml" >/dev/null || fail "apply failed"
k scale deployment/generator --replicas=1 >/dev/null || fail "generator scale failed"
for cj in java-loader python-loader; do
  k patch cronjob "$cj" -p '{"spec":{"suspend":false}}' >/dev/null || fail "resume $cj failed"
done
log "waiting for generator"
k rollout status deployment/generator --timeout=120s >/dev/null || fail "generator not ready"

for name in $(service_names); do
  port="$(service_port "$name")"
  if port_up "$port"; then
    log "$name already forwarded on $port"
    continue
  fi
  target="$(service_target "$name")"
  nohup kubectl --context "$CTX" port-forward ${target% *} "$port:${target#* }" > "$RUN/logs/$name.log" 2>&1 &
  echo "$!" > "$RUN/$name.pid"
  wait_until 60 port_up "$port" || fail "port-forward for $name did not open $port, see $RUN/logs/$name.log"
done

log "cronjobs java-loader and python-loader run every minute"
for name in $(service_names); do
  log "$name: $(service_url "$name")"
done
