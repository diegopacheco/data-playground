#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

for tool in podman kind kubectl uv mvn lsof curl; do require "$tool"; done
[ -x "$JAVA_HOME/bin/java" ] || fail "Java 25 not found at $JAVA_HOME"

if cluster_exists; then
  log "kind cluster $CLUSTER already exists"
else
  sed "s|\${RESULTS_HOST_PATH}|$RESULTS|" "$ROOT/k8s/kind.yaml" > "$RUN/kind.yaml"
  kind create cluster --config "$RUN/kind.yaml" || fail "kind create cluster failed"
fi

log "syncing python projects"
(cd "$ROOT/etl-python" && uv sync --python 3.15 --quiet) || fail "uv sync etl-python failed"
(cd "$ROOT/e2e" && uv sync --python 3.15 --quiet) || fail "uv sync e2e failed"

log "building java etl jar"
(cd "$ROOT/etl-java" && mvn -q -B package -DskipTests) || fail "maven package failed"

podman build -t "$PY_IMAGE" -f "$ROOT/etl-python/Containerfile" "$ROOT/etl-python" || fail "python image build failed"
podman build -t "$JAVA_IMAGE" -f "$ROOT/etl-java/Containerfile" "$ROOT/etl-java" || fail "java image build failed"
for image in "$KUEUE_IMAGE" "$KUEUEVIZ_BACKEND_IMAGE" "$KUEUEVIZ_FRONTEND_IMAGE"; do
  podman image exists "$image" || podman pull "$image" || fail "pull $image failed"
done
for image in "$KUEUE_IMAGE" "$KUEUEVIZ_BACKEND_IMAGE" "$KUEUEVIZ_FRONTEND_IMAGE" "$PY_IMAGE" "$JAVA_IMAGE"; do
  log "loading $image into kind"
  load_image "$image"
done

log "installing kueue $KUEUE_VERSION"
manifests="$(vendor_file manifests.yaml)"
k apply --server-side --force-conflicts -f "$manifests" >/dev/null || fail "kueue install failed"
k apply --server-side --force-conflicts -f "$ROOT/k8s/kueue-config.yaml" >/dev/null || fail "kueue config apply failed"
k -n kueue-system rollout restart deployment kueue-controller-manager >/dev/null || fail "kueue restart failed"
k -n kueue-system rollout status deployment kueue-controller-manager --timeout=120s >/dev/null || fail "kueue controller not ready, see: kubectl --context $CTX -n kueue-system logs deploy/kueue-controller-manager"
vendor_file kueueviz-single-host.yaml >/dev/null
log "setup done"
