#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

if cluster_exists; then
  log "cluster $CLUSTER UP"
  k get deployments -A --no-headers 2>/dev/null | awk '$1=="argo"||$1=="'"$NAMESPACE"'"{print "  " $1 "/" $2 " ready=" $3}'
  k -n "$NAMESPACE" get cronworkflows --no-headers 2>/dev/null | awk '{print "  cronworkflow " $1}'
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
