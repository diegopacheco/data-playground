#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

cluster_exists || fail "cluster $CLUSTER missing, run scripts/setup.sh first"

k apply -f "$ROOT/k8s/kafka.yaml" >/dev/null || fail "kafka apply failed"
log "waiting for kafka"
wait_long kafka_ready || fail "kafka not ready, see: kubectl --context $CTX logs kafka-0"
for variant in $VARIANTS; do
  k exec kafka-0 -- /opt/kafka/bin/kafka-topics.sh --bootstrap-server localhost:9092 --create --if-not-exists \
    --topic "orders-$variant" --partitions 1 --replication-factor 1 >/dev/null || fail "topic orders-$variant failed"
done

k apply -f "$ROOT/k8s/lab.yaml" >/dev/null || fail "lab apply failed"
wait_deployments default || fail "lab not ready, see: kubectl --context $CTX logs deploy/lab"

k apply -f "$ROOT/k8s/services.yaml" >/dev/null || fail "knative services apply failed"
for variant in $VARIANTS; do
  log "waiting for knative service orders-$variant"
  wait_long condition_ready ksvc "orders-$variant" || fail "ksvc orders-$variant not ready"
done

k apply -f "$ROOT/k8s/sources.yaml" >/dev/null || fail "kafka sources apply failed"
for variant in $VARIANTS; do
  log "waiting for kafka source orders-$variant"
  wait_long condition_ready kafkasource "orders-$variant" || fail "kafkasource orders-$variant not ready"
done

for name in $(service_names); do
  port="$(service_port "$name")"
  if port_up "$port"; then
    log "$name already forwarded on $port"
    continue
  fi
  target="$(service_target "$name")"
  nohup kubectl --context "$CTX" port-forward ${target% *} "$port:${target##* }" > "$RUN/logs/$name.log" 2>&1 &
  echo "$!" > "$RUN/$name.pid"
  wait_until 60 port_up "$port" || fail "port-forward for $name did not open $port, see $RUN/logs/$name.log"
done

for name in $(service_names); do
  log "$name: $(service_url "$name")"
done
