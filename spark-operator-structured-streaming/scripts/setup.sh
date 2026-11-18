#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

for tool in podman kind kubectl helm uv mvn lsof; do require "$tool"; done
[ -x "$JAVA_HOME/bin/java" ] || fail "Java 25 not found at $JAVA_HOME"
[ -x "$JAVA21_HOME/bin/java" ] || fail "Java 21 not found at $JAVA21_HOME, PySpark unit tests run on the Spark runtime JDK"

if cluster_exists; then
  log "kind cluster $CLUSTER already exists"
else
  kind create cluster --config "$ROOT/k8s/kind.yaml" || fail "kind create cluster failed"
fi

log "syncing python projects"
(cd "$ROOT/python-job" && uv sync --python 3.14 --quiet) || fail "uv sync python-job failed"
(cd "$ROOT/producer" && uv sync --python 3.15 --quiet) || fail "uv sync producer failed"
(cd "$ROOT/e2e" && uv sync --python 3.15 --quiet) || fail "uv sync e2e failed"

log "building java job jar"
(cd "$ROOT/java-job" && mvn -q -B package -DskipTests) || fail "maven package failed"

for image in $SPARK_BASE_IMAGE $UV_IMAGE $OPERATOR_IMAGE $INFRA_IMAGES docker.io/library/python:3.15.2-slim; do
  podman image exists "$image" || podman pull -q "$image" >/dev/null || fail "pull $image failed"
done
podman build -q -t "$SPARK_IMAGE" -f "$ROOT/spark-image/Containerfile" "$ROOT" >/dev/null || fail "spark image build failed"
podman build -q -t "$PRODUCER_IMAGE" -f "$ROOT/producer/Containerfile" "$ROOT/producer" >/dev/null || fail "producer image build failed"

for image in $OPERATOR_IMAGE $INFRA_IMAGES "$SPARK_IMAGE" "$PRODUCER_IMAGE"; do
  log "loading $image into kind"
  load_image "$image"
done

log "installing kubeflow spark operator $OPERATOR_VERSION"
attempt=0
until helm --kube-context "$CTX" upgrade --install spark-operator spark-operator --repo "$OPERATOR_REPO" --version "$OPERATOR_VERSION" \
  -n spark-operator --create-namespace --set image.tag="$OPERATOR_VERSION" \
  --wait --timeout 5m >"$RUN/logs/helm.log" 2>&1; do
  attempt=$((attempt + 1))
  [ "$attempt" -lt 5 ] || fail "helm install failed, see $RUN/logs/helm.log"
  sleep 1
done
wait_long 3 deploy_ready spark-operator spark-operator-controller || fail "operator controller not ready"
wait_long 3 deploy_ready spark-operator spark-operator-webhook || fail "operator webhook not ready"
log "setup done"
