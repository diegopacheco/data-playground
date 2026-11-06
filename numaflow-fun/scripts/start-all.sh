#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

cluster_exists || fail "cluster $CLUSTER missing, run scripts/setup.sh first"

k apply -f "$ROOT/k8s/pipeline.yaml" >/dev/null || fail "pipeline apply failed"
log "waiting for pipeline $PIPELINE"
wait_until 60 k get svc "$PIPELINE-in" || fail "service $PIPELINE-in not created"
wait_pods -l "numaflow.numaproj.io/pipeline-name=$PIPELINE" || fail "pipeline pods not ready"

for name in $(service_names); do
  port="$(service_port "$name")"
  if port_up "$port"; then
    log "$name already forwarded on $port"
    continue
  fi
  nohup kubectl --context "$CTX" port-forward $(service_target "$name") "$port:8443" > "$RUN/logs/$name.log" 2>&1 &
  echo "$!" > "$RUN/$name.pid"
  wait_until 60 port_up "$port" || fail "port-forward for $name did not open $port, see $RUN/logs/$name.log"
done

for name in $(service_names); do
  log "$name: $(service_url "$name")"
done
