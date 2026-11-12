#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

state_of() {
  if "$@"; then printf "READY"; else printf "ABSENT"; fi
}

if cluster_exists; then
  log "cluster $CLUSTER UP"
  for ns in knative-serving kourier-system knative-eventing; do
    log "  $ns $(state_of deployments_ready "$ns")"
  done
  log "  kafka $(state_of kafka_ready)"
  for variant in $VARIANTS; do
    pods="$(k get pods -l "serving.knative.dev/service=orders-$variant" --no-headers 2>/dev/null | wc -l | tr -d ' ')"
    log "  orders-$variant ksvc $(state_of condition_ready ksvc "orders-$variant"), source $(state_of condition_ready kafkasource "orders-$variant"), pods $pods"
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
