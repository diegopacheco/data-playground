#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

for tool in podman kind kubectl mvn uv lsof curl; do require "$tool"; done
[ -x "$JAVA_HOME/bin/java" ] || fail "JDK 25 not found at $JAVA_HOME"

if cluster_exists; then
  log "kind cluster $CLUSTER already exists"
else
  kind create cluster --config "$ROOT/k8s/kind.yaml" || fail "kind create cluster failed"
fi

kubectl --context "$CTX" create namespace "$NS" --dry-run=client -o yaml | kubectl --context "$CTX" apply -f - >/dev/null
operator_yaml="$RUN/strimzi-cluster-operator-$STRIMZI_VERSION.yaml"
if [ ! -s "$operator_yaml" ]; then
  curl -fsSL "https://github.com/strimzi/strimzi-kafka-operator/releases/download/$STRIMZI_VERSION/strimzi-cluster-operator-$STRIMZI_VERSION.yaml" \
    | sed "s/namespace: myproject/namespace: $NS/" > "$operator_yaml" || fail "strimzi download failed"
fi
k apply --server-side --force-conflicts -f "$operator_yaml" >/dev/null || fail "strimzi install failed"
log "waiting for strimzi cluster operator $STRIMZI_VERSION"
wait_long 5 pods_ready -l name=strimzi-cluster-operator || fail "strimzi operator not ready"

k apply -f "$ROOT/k8s/kafka.yaml" >/dev/null || fail "kafka apply failed"
log "waiting for kafka $KAFKA (3 controllers, 3 brokers, cruise control)"
wait_long 15 resource_ready "kafka/$KAFKA" || fail "kafka $KAFKA not ready"

k apply -f "$ROOT/k8s/topics.yaml" -f "$ROOT/k8s/users.yaml" >/dev/null || fail "topics or users apply failed"
for r in kafkatopic/orders kafkauser/order-producer kafkauser/order-consumer kafkauser/cluster-inspector; do
  wait_long 3 resource_ready "$r" || fail "$r not ready"
done
log "topic and users ready"

(cd "$ROOT/producer" && mvn -q -B -DskipTests package) || fail "producer build failed"
(cd "$ROOT/consumer" && uv lock -q) || fail "consumer lock failed"
podman build -t "$PRODUCER_IMAGE" -f "$ROOT/producer/Containerfile" "$ROOT/producer" || fail "producer image build failed"
podman build -t "$CONSUMER_IMAGE" -f "$ROOT/consumer/Containerfile" "$ROOT/consumer" || fail "consumer image build failed"
for image in "$PRODUCER_IMAGE" "$CONSUMER_IMAGE"; do
  podman save -o "$RUN/image.tar" "$image" || fail "image save failed for $image"
  kind load image-archive "$RUN/image.tar" --name "$CLUSTER" || fail "kind load failed for $image"
  rm -f "$RUN/image.tar"
done
log "setup done"
