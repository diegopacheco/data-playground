#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

if cluster_exists; then
  phase="$(k get pipeline "$PIPELINE" -o jsonpath='{.status.phase}' 2>/dev/null || true)"
  log "cluster $CLUSTER UP, pipeline $PIPELINE ${phase:-ABSENT}"
else
  log "cluster $CLUSTER DOWN"
fi

for name in $(service_names); do
  port="$(service_port "$name")"
  if port_up "$port"; then
    log "$name $port UP pid=$(port_pid "$port") $(service_url "$name")"
  else
    log "$name $port DOWN"
  fi
done
