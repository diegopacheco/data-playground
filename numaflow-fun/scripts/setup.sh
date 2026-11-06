#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

for tool in podman kind kubectl python3.15 lsof curl; do require "$tool"; done

if cluster_exists; then
  log "kind cluster $CLUSTER already exists"
else
  kind create cluster --config "$ROOT/k8s/kind.yaml" || fail "kind create cluster failed"
fi

k create namespace numaflow-system --dry-run=client -o yaml | k apply -f - >/dev/null
k apply -n numaflow-system -f "https://raw.githubusercontent.com/numaproj/numaflow/$NUMAFLOW_VERSION/config/install.yaml" >/dev/null || fail "numaflow install failed"
log "waiting for numaflow controller and server"
wait_pods -n numaflow-system || fail "numaflow pods not ready"

k apply -f "$ROOT/k8s/isbsvc.yaml" >/dev/null || fail "isbsvc apply failed"
log "waiting for jetstream isb service"
wait_until 60 k get statefulset isbsvc-default-js || fail "isbsvc statefulset not created"
wait_pods -l app.kubernetes.io/component=isbsvc || fail "isbsvc pods not ready"

podman build -t "$IMAGE" -f "$ROOT/Containerfile" "$ROOT" || fail "image build failed"
podman save -o "$RUN/udf.tar" "$IMAGE" || fail "image save failed"
kind load image-archive "$RUN/udf.tar" --name "$CLUSTER" || fail "kind load failed"
rm -f "$RUN/udf.tar"
log "setup done"
