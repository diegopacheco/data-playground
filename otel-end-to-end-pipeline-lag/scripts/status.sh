#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

if cluster_exists; then
  log "cluster $CLUSTER UP"
  for app in $INFRA order-producer lag-consumer; do
    if pods_ready -l "app=$app"; then log "$app READY"; else log "$app NOT READY"; fi
  done
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
