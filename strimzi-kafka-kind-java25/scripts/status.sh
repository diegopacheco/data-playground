#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

if cluster_exists; then
  kafka_ready="$(k get "kafka/$KAFKA" -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}' 2>/dev/null || true)"
  brokers="$(k get kafkanodepool brokers -o jsonpath='{.status.nodeIds}' 2>/dev/null || true)"
  log "cluster $CLUSTER UP, kafka $KAFKA ready=${kafka_ready:-ABSENT}, broker ids ${brokers:-none}"
  for app in order-producer order-consumer; do
    ready="$(k get deploy "$app" -o jsonpath='{.status.readyReplicas}' 2>/dev/null || true)"
    log "$app ready=${ready:-0}"
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
