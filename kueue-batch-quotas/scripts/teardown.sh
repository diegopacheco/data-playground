#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

"$SCRIPTS/stop-all.sh"
if cluster_exists; then
  kind delete cluster --name "$CLUSTER" || fail "kind delete cluster failed"
fi
for image in "$PY_IMAGE" "$JAVA_IMAGE" "$KUEUE_IMAGE" "$KUEUEVIZ_BACKEND_IMAGE" "$KUEUEVIZ_FRONTEND_IMAGE"; do
  if podman image exists "$image"; then
    podman rmi "$image" >/dev/null || fail "podman rmi $image failed"
    log "removed $image"
  fi
done
log "teardown done"
