#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

cluster_exists || fail "cluster $CLUSTER missing, run scripts/setup.sh first"

for broker in iggy kafka; do
  k apply -f "$ROOT/k8s/$broker.yaml" >/dev/null || fail "$broker apply failed"
done
for broker in iggy kafka; do
  log "waiting for $broker"
  wait_until 60 broker_ready "$broker" || wait_until 60 broker_ready "$broker" || fail "$broker not ready, see: kubectl --context $CTX logs $broker-0"
done

for name in $(service_names); do
  port="$(service_port "$name")"
  if port_up "$port"; then
    log "$name already forwarded on $port"
    continue
  fi
  target="$(service_target "$name")"
  nohup kubectl --context "$CTX" port-forward ${target% *} "$port:${target##* }" > "$RUN/logs/$name.log" 2>&1 &
  echo "$!" > "$RUN/$name.pid"
  wait_until 60 port_up "$port" || fail "port-forward for $name did not open $port, see $RUN/logs/$name.log"
done

for name in $(service_names); do
  log "$name: $(service_url "$name")"
done
