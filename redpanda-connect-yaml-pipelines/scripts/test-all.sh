#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require podman
for name in ui connect proxy postgres; do
  port_up "$(service_port "$name")" || fail "$name is down, run scripts/start-all.sh first"
done
mkdir -p "$RUN/logs"

log "redpanda connect unit tests (rpk connect test)"
status=0
podman run --rm -v "$ROOT:/connect:ro" "$CONNECT_IMAGE" test -r /connect/resources/caches.yaml \
  /connect/tests/connect/validate_order_test.yaml /connect/tests/connect/price_order_test.yaml /connect/tests/connect/orders_pipeline_test.yaml \
  >"$RUN/logs/connect-tests.log" 2>&1 || status=$?
cat "$RUN/logs/connect-tests.log"
[ "$status" = "0" ] || fail "connect unit tests failed, see .run/logs/connect-tests.log"

log "end to end tests against the running pipelines"
status=0
podman exec t5-ui python -m unittest -v tests.test_pipelines >"$RUN/logs/e2e.log" 2>&1 || status=$?
cat "$RUN/logs/e2e.log"
[ "$status" = "0" ] || fail "end to end tests failed, see .run/logs/e2e.log"
log "all tests passed"
