#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

if cluster_exists; then
  states=""
  for broker in iggy kafka; do
    if broker_ready "$broker"; then state="READY"; else state="ABSENT"; fi
    states="$states, $broker $state"
  done
  jobs="$(k get jobs -l app=bench --no-headers 2>/dev/null | wc -l | tr -d ' ')"
  log "cluster $CLUSTER UP$states, bench jobs $jobs"
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
