#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

for name in $(service_names); do
  pid="$(forward_pid "$name")"
  [ -n "$pid" ] && kill "$pid" 2>/dev/null || true
  rm -f "$RUN/$name.pid"
done

if cluster_exists; then
  kind delete cluster --name "$CLUSTER" || fail "kind delete cluster failed"
fi
for image in "$JAVA_IMAGE" "$PYTHON_IMAGE"; do
  if podman image exists "$image"; then
    podman rmi "$image" >/dev/null || fail "podman rmi $image failed"
  fi
done
log "cluster $CLUSTER and local images removed"
