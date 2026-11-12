#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

"$SCRIPTS/stop-all.sh"
if cluster_exists; then
  kind delete cluster --name "$CLUSTER" || fail "kind delete cluster failed"
fi
for variant in $VARIANTS lab; do
  image="$(image_for "$variant")"
  if podman image exists "$image"; then
    podman rmi "$image" >/dev/null || fail "podman rmi $image failed"
    log "removed $image"
  fi
done
log "teardown done"
