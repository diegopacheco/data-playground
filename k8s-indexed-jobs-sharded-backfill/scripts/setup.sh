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
(cd "$ROOT/python-worker" && uv sync --python 3.15 --quiet) || fail "uv sync python-worker failed"
(cd "$ROOT/e2e" && uv sync --python 3.15 --quiet) || fail "uv sync e2e failed"

log "building java worker jar"
(cd "$ROOT/java-worker" && mvn -q -B package -DskipTests) || fail "maven package failed"

podman build -t "$PY_IMAGE" -f "$ROOT/python-worker/Containerfile" "$ROOT/python-worker" || fail "python image build failed"
podman build -t "$JAVA_IMAGE" -f "$ROOT/java-worker/Containerfile" "$ROOT/java-worker" || fail "java image build failed"
podman image exists "$PG_IMAGE" || podman pull "$PG_IMAGE" || fail "pull $PG_IMAGE failed"

for image in "$PG_IMAGE" "$PY_IMAGE" "$JAVA_IMAGE"; do
  log "loading $image into kind"
  load_image "$image"
done
log "setup done"
