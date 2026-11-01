#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require podman
port_up "$(service_port ui)" || fail "ui is down, run scripts/start-all.sh first"

mkdir -p "$RUN/logs"
log "running the h3 tests inside $APP_CONTAINER"
status=0
podman exec "$APP_CONTAINER" python -m unittest -v tests.test_h3 >"$RUN/logs/tests.log" 2>&1 || status=$?
cat "$RUN/logs/tests.log"
[ "$status" = "0" ] || fail "h3 tests failed, see .run/logs/tests.log"
log "all tests passed"
