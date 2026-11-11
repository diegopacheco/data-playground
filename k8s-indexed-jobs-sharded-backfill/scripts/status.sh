#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

if cluster_exists; then
  if postgres_ready; then pg="READY"; else pg="ABSENT"; fi
  jobs="$(k get jobs -l app=backfill --no-headers 2>/dev/null | wc -l | tr -d ' ')"
  log "cluster $CLUSTER UP, postgres $pg, backfill jobs $jobs"
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
