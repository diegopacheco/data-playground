#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

for tool in podman kind kubectl mvn uv lsof openssl; do require "$tool"; done
[ -x "$JAVA_HOME/bin/java" ] || fail "JDK 25 not found at $JAVA_HOME"

if cluster_exists; then
  log "kind cluster $CLUSTER already exists"
else
  kind create cluster --config "$ROOT/k8s/kind.yaml" || fail "kind create cluster failed"
fi

load_image() {
  podman image exists "$1" || podman pull -q "$1" >/dev/null || fail "pull failed for $1"
  podman save -o "$RUN/image.tar" "$1" >/dev/null || fail "image save failed for $1"
  kind load image-archive "$RUN/image.tar" --name "$CLUSTER" >/dev/null || fail "kind load failed for $1"
  rm -f "$RUN/image.tar"
}

for image in $(grep -h 'image: docker.io' "$ROOT"/k8s/*.yaml | awk '{print $2}' | sort -u); do
  log "loading $image"
  load_image "$image"
done

kubectl --context "$CTX" create namespace "$NS" --dry-run=client -o yaml | kubectl --context "$CTX" apply -f - >/dev/null
if ! k get secret postgres >/dev/null 2>&1; then
  k create secret generic postgres --from-literal=password="$(openssl rand -hex 16)" >/dev/null || fail "postgres secret failed"
fi
configmap_from otel-collector-config --from-file="$ROOT/k8s/otel-collector/config.yaml"
configmap_from prometheus-config --from-file="$ROOT/k8s/prometheus/prometheus.yml" --from-file="$ROOT/k8s/prometheus/rules.yml"
configmap_from grafana-datasources --from-file="$ROOT/k8s/grafana/datasources.yaml"
configmap_from grafana-providers --from-file="$ROOT/k8s/grafana/providers.yaml"
configmap_from grafana-dashboards --from-file="$ROOT/k8s/grafana/pipeline-lag.json"

for part in $INFRA; do
  k apply -f "$ROOT/k8s/$part.yaml" >/dev/null || fail "$part apply failed"
done
for part in $INFRA; do
  log "waiting for $part"
  wait_long 5 pods_ready -l "app=$part" || fail "$part not ready"
done

k exec kafka-0 -- /opt/kafka/bin/kafka-topics.sh --bootstrap-server localhost:9092 \
  --create --if-not-exists --topic "$TOPIC" --partitions 3 --replication-factor 1 >/dev/null || fail "topic $TOPIC create failed"
log "topic $TOPIC ready"

(cd "$ROOT/producer" && mvn -q -B -DskipTests package) || fail "producer build failed"
(cd "$ROOT/consumer" && uv lock -q) || fail "consumer lock failed"
podman build -q -t "$PRODUCER_IMAGE" -f "$ROOT/producer/Containerfile" "$ROOT/producer" >/dev/null || fail "producer image build failed"
podman build -q -t "$CONSUMER_IMAGE" -f "$ROOT/consumer/Containerfile" "$ROOT/consumer" >/dev/null || fail "consumer image build failed"
for image in "$PRODUCER_IMAGE" "$CONSUMER_IMAGE"; do
  log "loading $image"
  load_image "$image"
done
log "setup done"
