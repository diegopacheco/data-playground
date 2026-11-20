#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require podman
require node
for name in $(service_names); do
  port_up "$(service_port "$name")" || fail "$name is down, run scripts/start-all.sh first"
done

mkdir -p "$RUN/logs"
log "running every scenario against the primary and the 3 embedded replicas"
api_post run-all >/dev/null || fail "scenarios failed, see: podman logs t6-console"

status=0
podman exec t6-console node --test --test-reporter=spec tests/replicas.test.js >"$RUN/logs/tests.log" 2>&1 || status=$?
cat "$RUN/logs/tests.log"
[ "$status" = "0" ] || fail "replica tests failed, see .run/logs/tests.log"

log "stopping t6-sqld to test reads during a primary outage"
status=0
node --test --test-reporter=spec "$ROOT/tests/outage.test.js" >"$RUN/logs/outage.log" 2>&1 || status=$?
cat "$RUN/logs/outage.log"
[ "$status" = "0" ] || fail "outage test failed, see .run/logs/outage.log"
wait_until 60 primary_ready || fail "primary did not come back after the outage test"
log "all tests passed"
