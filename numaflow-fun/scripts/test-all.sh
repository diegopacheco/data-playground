#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

log "unit tests on host python3.15"
python3.15 -m unittest discover -s "$ROOT/tests" -p 'test_orders.py' -v || fail "host unit tests failed"

log "unit tests inside $IMAGE"
podman run --rm -v "$ROOT/tests:/tests:ro" --entrypoint python "$IMAGE" -m unittest discover -s /tests -p 'test_orders.py' || fail "image unit tests failed"

port_up "$(service_port orders_in)" || fail "orders_in is DOWN, run scripts/start-all.sh first"

log "curl smoke test"
order_id="curl-$(date +%s)-$$"
response="$(curl -sk -X POST "$(service_url orders_in)" \
  -H "X-Numaflow-Id: $order_id" \
  -d "{\"id\":\"$order_id\",\"qty\":2,\"price_cents\":7500}")" || fail "curl POST failed"
log "$response"
printf "%s" "$response" | grep -q "\"message\":\"Data received successfully\",\"id\":\"$order_id\"" || fail "unexpected response: $response"
in_big_sink() {
  k logs --tail=-1 -c udsink -l "numaflow.numaproj.io/pipeline-name=$PIPELINE,numaflow.numaproj.io/vertex-name=big" | grep -q "\"id\": \"$order_id\""
}
wait_until 60 in_big_sink || fail "$order_id did not reach the big sink"
log "$order_id reached the big sink"

log "pipeline integration test"
ORDERS_URL="$(service_url orders_in)" KUBE_CONTEXT="$CTX" PIPELINE="$PIPELINE" \
  python3.15 -m unittest discover -s "$ROOT/tests" -p 'test_pipeline.py' -v || fail "pipeline integration test failed"
log "all tests passed"
