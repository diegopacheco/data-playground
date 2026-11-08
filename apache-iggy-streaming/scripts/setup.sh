#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

for tool in podman kind kubectl uv mvn lsof; do require "$tool"; done
[ -x "$JAVA_HOME/bin/java" ] || fail "Java 25 not found at $JAVA_HOME"

if cluster_exists; then
  log "kind cluster $CLUSTER already exists"
else
  kind create cluster --config "$ROOT/k8s/kind.yaml" || fail "kind create cluster failed"
fi

log "syncing python projects"
(cd "$ROOT/python-bench" && uv sync --python 3.15 --quiet) || fail "uv sync python-bench failed"
(cd "$ROOT/e2e" && uv sync --python 3.15 --quiet) || fail "uv sync e2e failed"

log "building java bench jar"
(cd "$ROOT/java-bench" && mvn -q -B package -DskipTests) || fail "maven package failed"

log "building python bench image, the Iggy SDK has no cp315 wheel so it compiles from source"
podman build -t "$PY_IMAGE" -f "$ROOT/python-bench/Containerfile" "$ROOT/python-bench" || fail "python image build failed"
podman build -t "$JAVA_IMAGE" -f "$ROOT/java-bench/Containerfile" "$ROOT/java-bench" || fail "java image build failed"
for image in "$IGGY_IMAGE" "$KAFKA_IMAGE"; do
  podman image exists "$image" || podman pull "$image" || fail "pull $image failed"
done

for image in "$IGGY_IMAGE" "$KAFKA_IMAGE" "$PY_IMAGE" "$JAVA_IMAGE"; do
  log "loading $image into kind"
  load_image "$image"
done
log "setup done"
