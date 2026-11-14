#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

cluster_exists || fail "cluster $CLUSTER missing, run scripts/setup.sh first"
wait_until 60 kueue_ready || fail "kueue controller not ready, run scripts/setup.sh"

log "applying flavor, priority classes, team namespaces, cluster queues and local queues"
wait_until 60 k apply -f "$ROOT/k8s/queues.yaml" || k apply -f "$ROOT/k8s/queues.yaml" >/dev/null || fail "queues apply failed, the kueue webhook may not be ready"

log "deploying kueueviz"
k apply --server-side --force-conflicts -f "$(vendor_file kueueviz-single-host.yaml)" >/dev/null || fail "kueueviz apply failed"
sed "s|\${BACKEND_URL}|$(service_url kueueviz-backend)|" "$ROOT/k8s/kueueviz-env.yaml" | k apply --server-side --force-conflicts -f - >/dev/null || fail "kueueviz env apply failed"
k -n kueue-system rollout restart deployment kueue-kueueviz-frontend >/dev/null || fail "kueueviz restart failed"
for name in kueue-kueueviz-backend kueue-kueueviz-frontend; do
  k -n kueue-system rollout status deployment "$name" --timeout=120s >/dev/null || fail "$name not ready"
done

for name in $(service_names); do
  port="$(service_port "$name")"
  if port_up "$port"; then
    log "$name already forwarded on $port"
    continue
  fi
  nohup kubectl --context "$CTX" -n kueue-system port-forward "$(service_target "$name")" "$port:8080" > "$RUN/logs/$name.log" 2>&1 &
  echo "$!" > "$RUN/$name.pid"
  wait_until 60 port_up "$port" || fail "port-forward for $name did not open $port, see $RUN/logs/$name.log"
done

for name in $(service_names); do
  log "$name: $(service_url "$name")"
done
