#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

cluster_exists || fail "cluster $CLUSTER missing, run scripts/setup.sh first"
deploy_ready spark-operator spark-operator-controller || fail "operator not ready, run scripts/setup.sh first"

log "starting minio, postgres and kafka"
k apply -f "$ROOT/k8s/storage.yaml" -f "$ROOT/k8s/kafka.yaml" >/dev/null || fail "storage apply failed"
wait_long 3 deploy_ready default minio || fail "minio not ready"
wait_long 3 deploy_ready default postgres || fail "postgres not ready"
wait_long 3 kafka_ready || fail "kafka not ready"

k exec deploy/minio -- sh -c 'mc alias set local http://127.0.0.1:9000 lakeadmin lakeadmin-secret >/dev/null && mc mb -p local/lake local/checkpoints >/dev/null' || fail "bucket creation failed"
k exec kafka-0 -- /opt/kafka/bin/kafka-topics.sh --bootstrap-server localhost:9092 --create --if-not-exists \
  --topic "$TOPIC" --partitions "$TOPIC_PARTITIONS" --replication-factor 1 >/dev/null || fail "topic creation failed"

log "starting producer and lake-query"
k apply -f "$ROOT/k8s/producer.yaml" -f "$ROOT/k8s/lake-query.yaml" >/dev/null || fail "producer apply failed"
wait_long 2 deploy_ready default producer || fail "producer not ready"
wait_long 2 deploy_ready default lake-query || fail "lake-query not ready"

for app in $APPS; do
  if [ -n "$(k get sparkapplication "$app" -o name --ignore-not-found)" ]; then
    log "$app already deployed"
  else
    k apply -f "$ROOT/k8s/$app.yaml" >/dev/null || fail "$app apply failed"
  fi
done
for app in $APPS; do
  log "waiting for $app to be RUNNING"
  wait_long 5 app_running "$app" || fail "$app not running, state=$(app_state "$app")"
done

for name in $(service_names); do
  port="$(service_port "$name")"
  if port_up "$port"; then
    log "$name already forwarded on $port"
    continue
  fi
  target="$(service_target "$name")"
  nohup bash -c "while true; do kubectl --context '$CTX' port-forward ${target% *} '$port:${target##* }'; sleep 1; done" > "$RUN/logs/$name.log" 2>&1 &
  echo "$!" > "$RUN/$name.pid"
  wait_until 60 port_up "$port" || fail "port-forward for $name did not open $port, see $RUN/logs/$name.log"
done

for name in $(service_names); do
  log "$name: $(service_url "$name")"
done
