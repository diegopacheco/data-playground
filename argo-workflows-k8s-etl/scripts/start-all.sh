#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

[ -s "$ARGO_INSTALL" ] || fail "argo install manifest missing, run scripts/setup.sh first"
podman image exists "$APP_IMAGE" || fail "$APP_IMAGE missing, run scripts/setup.sh first"

if cluster_exists; then
  log "kind cluster $CLUSTER already exists"
else
  render "$ROOT/k8s/kind.yaml" > "$RUN/kind.yaml"
  kind create cluster --config "$RUN/kind.yaml" || fail "kind create cluster failed"
fi
podman update --memory "$NODE_MEMORY" --memory-swap "$NODE_MEMORY" "$NODE" >/dev/null || fail "could not limit $NODE memory"

podman save -o "$RUN/app-image.tar" "$APP_IMAGE" || fail "image save failed"
kind load image-archive "$RUN/app-image.tar" --name "$CLUSTER" || fail "kind load failed"
rm -f "$RUN/app-image.tar"

k create namespace argo --dry-run=client -o yaml | k apply -f - >/dev/null
k apply --server-side --force-conflicts -n argo -f "$ARGO_INSTALL" >/dev/null || fail "argo install failed"
render "$ROOT/k8s/argo-config.yaml" | k apply --server-side --force-conflicts -f - >/dev/null || fail "argo config failed"
k -n argo patch deployment argo-server --type json --patch-file "$ROOT/k8s/argo-server-patch.json" >/dev/null || fail "argo-server patch failed"
k -n argo patch deployment workflow-controller --type json --patch-file "$ROOT/k8s/controller-patch.json" >/dev/null || fail "workflow-controller patch failed"
render "$ROOT/k8s/stack.yaml" | k apply -f - >/dev/null || fail "stack apply failed"
k -n "$NAMESPACE" rollout restart deployment t8-ui >/dev/null
k apply -f "$ROOT/k8s/workflow-template.yaml" -f "$ROOT/k8s/cron-workflow.yaml" >/dev/null || fail "workflow apply failed"

log "waiting for argo and the etl stack"
for name in workflow-controller argo-server; do
  wait_rollout argo "$name" || fail "$name not ready"
done
for name in t8-minio t8-postgres t8-ui; do
  wait_rollout "$NAMESPACE" "$name" || fail "$name not ready"
done

wait_until 60 http_ok "$(service_url argo_ui)/api/v1/version" || fail "argo ui not answering on $(service_url argo_ui)"
wait_until 60 http_ok "$(service_url etl_ui)/api/cron" || fail "etl ui not answering on $(service_url etl_ui)"
wait_until 60 port_up "$(service_port postgres)" || fail "postgres port $(service_port postgres) not open"

for name in $(service_names); do
  log "$name: $(service_url "$name")"
done
