#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

for tool in podman kind kubectl helm uv mvn lsof; do require "$tool"; done
[ -x "$JAVA_HOME/bin/java" ] || fail "Java 25 not found at $JAVA_HOME"

if cluster_exists; then
  log "kind cluster $CLUSTER already exists"
else
  kind create cluster --config "$ROOT/k8s/kind.yaml" || fail "kind create cluster failed"
fi

log "syncing python projects"
(cd "$ROOT/etl" && uv sync --python 3.14 --quiet) || fail "uv sync etl failed"
(cd "$ROOT/e2e" && uv sync --python 3.15 --quiet) || fail "uv sync e2e failed"

log "building producer jar"
(cd "$ROOT/producer" && mvn -q -B package -DskipTests) || fail "maven package failed"

for image in "$RAY_IMAGE" "$JRE_IMAGE" "$MINIO_IMAGE" "$OPERATOR_IMAGE"; do
  podman image exists "$image" || podman pull "$image" || fail "pull $image failed"
done
podman build -t "$ETL_IMAGE" -f "$ROOT/etl/Containerfile" "$ROOT/etl" || fail "etl image build failed"
podman build -t "$PRODUCER_IMAGE" -f "$ROOT/producer/Containerfile" "$ROOT/producer" || fail "producer image build failed"

for image in "$OPERATOR_IMAGE" "$MINIO_IMAGE" "$PRODUCER_IMAGE" "$ETL_IMAGE"; do
  log "loading $image into kind"
  load_image "$image"
done

log "installing kuberay operator $KUBERAY_VERSION"
helm --kube-context "$CTX" upgrade --install kuberay-operator kuberay-operator --repo "$KUBERAY_REPO" \
  --version "$KUBERAY_VERSION" -n default --set image.pullPolicy=IfNotPresent \
  --wait --timeout 5m >"$RUN/logs/helm.log" 2>&1 || fail "helm install failed, see $RUN/logs/helm.log"
wait_long 3 deploy_ready default kuberay-operator || fail "kuberay operator not ready"
log "setup done"
