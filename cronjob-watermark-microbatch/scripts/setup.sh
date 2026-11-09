#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

for tool in podman kind kubectl mvn uv lsof; do require "$tool"; done
[ -x "$JAVA_HOME/bin/java" ] || fail "JDK 25 not found at $JAVA_HOME"

if cluster_exists; then
  log "kind cluster $CLUSTER already exists"
else
  kind create cluster --config "$ROOT/k8s/kind.yaml" || fail "kind create cluster failed"
fi

log "building java loader jar"
(cd "$ROOT/java-loader" && mvn -q -B -DskipTests package) || fail "maven package failed"
log "locking python loader dependencies"
(cd "$ROOT/python-loader" && uv lock --python 3.15 -q) || fail "uv lock failed"

podman build -t "$JAVA_IMAGE" -f "$ROOT/java-loader/Containerfile" "$ROOT/java-loader" || fail "java image build failed"
podman build -t "$PYTHON_IMAGE" -f "$ROOT/python-loader/Containerfile" "$ROOT/python-loader" || fail "python image build failed"
podman image exists "$POSTGRES_IMAGE" || podman pull "$POSTGRES_IMAGE" || fail "postgres image pull failed"

for image in "$POSTGRES_IMAGE" "$JAVA_IMAGE" "$PYTHON_IMAGE"; do
  log "loading $image into kind"
  load_image "$image"
done

k create configmap postgres-schema --from-file=schema.sql="$ROOT/sql/schema.sql" --dry-run=client -o yaml | k apply -f - >/dev/null || fail "schema configmap apply failed"
k apply -f "$ROOT/k8s/postgres.yaml" >/dev/null || fail "postgres apply failed"
log "waiting for postgres"
k rollout status statefulset/postgres --timeout=120s >/dev/null || fail "postgres not ready"
wait_until 60 psql_exec -c "SELECT 1 FROM watermarks LIMIT 1" || fail "schema not created"
log "setup done"
