#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require podman
require python3
for name in ui nats1 nats2 nats3; do
  port_up "$(service_port "$name")" || fail "$name is down, run scripts/start-all.sh first"
done

mkdir -p "$RUN/logs"
log "running every scenario against the cluster"
api_post run-all >/dev/null || fail "scenarios failed, see: podman logs r8-app"

status=0
podman exec r8-app python -m unittest -v tests.test_streams >"$RUN/logs/tests.log" 2>&1 || status=$?
cat "$RUN/logs/tests.log"
[ "$status" = "0" ] || fail "stream tests failed, see .run/logs/tests.log"

log "stopping r8-nats-3 to test failover"
status=0
python3 -m unittest -v tests.test_failover >"$RUN/logs/failover.log" 2>&1 || status=$?
cat "$RUN/logs/failover.log"
[ "$status" = "0" ] || fail "failover test failed, see .run/logs/failover.log"
wait_until 60 jetstream_ready || fail "cluster did not heal after the failover test"
log "all tests passed"
