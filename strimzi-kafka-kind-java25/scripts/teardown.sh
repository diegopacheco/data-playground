#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

"$SCRIPTS/stop-all.sh" || fail "stop-all failed"
if cluster_exists; then
  kind delete cluster --name "$CLUSTER" || fail "kind delete cluster failed"
fi
for image in "$PRODUCER_IMAGE" "$CONSUMER_IMAGE"; do
  if podman image exists "$image"; then
    podman rmi "$image" >/dev/null || fail "could not remove $image"
  fi
done
log "teardown done"
