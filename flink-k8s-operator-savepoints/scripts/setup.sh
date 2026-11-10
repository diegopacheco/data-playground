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
(cd "$ROOT/python-job" && uv sync --python 3.12 --quiet) || fail "uv sync python-job failed"
(cd "$ROOT/e2e" && uv sync --python 3.15 --quiet) || fail "uv sync e2e failed"

log "building java job jar"
(cd "$ROOT/java-job" && mvn -q -B package -DskipTests) || fail "maven package failed"

podman image exists "$FLINK_IMAGE" || podman pull "$FLINK_IMAGE" || fail "pull $FLINK_IMAGE failed"
podman build -t "$JAVA_IMAGE" -f "$ROOT/java-job/Containerfile" "$ROOT/java-job" || fail "java image build failed"
podman build -t "$PY_IMAGE" -f "$ROOT/python-job/Containerfile" "$ROOT/python-job" || fail "python image build failed"
for image in $OPERATOR_IMAGE $CERT_MANAGER_IMAGES; do
  podman image exists "$image" || podman pull "$image" || fail "pull $image failed"
done

for image in $CERT_MANAGER_IMAGES $OPERATOR_IMAGE "$JAVA_IMAGE" "$PY_IMAGE"; do
  log "loading $image into kind"
  load_image "$image"
done

log "installing cert-manager $CERT_MANAGER_VERSION"
k apply -f "$CERT_MANAGER_MANIFEST" >/dev/null || fail "cert-manager apply failed"
for d in cert-manager cert-manager-webhook cert-manager-cainjector; do
  wait_long 3 deploy_ready cert-manager "$d" || fail "$d not ready"
done

log "installing flink kubernetes operator $OPERATOR_VERSION"
attempt=0
until helm --kube-context "$CTX" upgrade --install flink-kubernetes-operator "$OPERATOR_CHART" -n default \
  --set image.repository="${OPERATOR_IMAGE%:*}" --set image.tag="$OPERATOR_VERSION" --set image.pullPolicy=IfNotPresent \
  --wait --timeout 5m >"$RUN/logs/helm.log" 2>&1; do
  attempt=$((attempt + 1))
  [ "$attempt" -lt 5 ] || fail "helm install failed, see $RUN/logs/helm.log"
  sleep 1
done
wait_long 3 deploy_ready default flink-kubernetes-operator || fail "operator not ready"
log "setup done"
