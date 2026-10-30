#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

if cluster_exists; then
  log "deleting kind cluster $CLUSTER"
  kind delete cluster --name "$CLUSTER" || fail "kind delete cluster failed"
else
  log "kind cluster $CLUSTER already gone"
fi

if podman network exists "$NETWORK"; then
  podman network rm "$NETWORK" >/dev/null || fail "could not remove network $NETWORK"
fi

for name in $(service_names); do
  wait_port_down "$(service_port "$name")" || fail "port $(service_port "$name") still in use"
done
log "stopped"
