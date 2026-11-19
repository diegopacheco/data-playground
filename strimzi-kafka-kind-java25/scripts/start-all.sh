#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

cluster_exists || fail "cluster $CLUSTER missing, run scripts/setup.sh first"
resource_ready "kafka/$KAFKA" || fail "kafka $KAFKA not ready, run scripts/setup.sh first"

k apply -f "$ROOT/k8s/apps.yaml" >/dev/null || fail "apps apply failed"
log "waiting for producer and consumer"
wait_long 3 pods_ready -l app=order-producer || fail "producer not ready"
wait_long 3 pods_ready -l app=order-consumer || fail "consumer not ready"

for name in $(service_names); do
  port="$(service_port "$name")"
  if port_up "$port"; then
    log "$name already forwarded on $port"
    continue
  fi
  set -- $(service_target "$name")
  nohup kubectl --context "$CTX" -n "$NS" port-forward "$1" "$port:$2" > "$RUN/logs/$name.log" 2>&1 &
  echo "$!" > "$RUN/$name.pid"
  wait_until 60 port_up "$port" || fail "port-forward for $name did not open $port, see $RUN/logs/$name.log"
done

for name in $(service_names); do
  log "$name: $(service_url "$name")"
done
