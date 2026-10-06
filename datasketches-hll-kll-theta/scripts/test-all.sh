#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require podman
port_up "$(service_port ui)" || fail "ui is down, run scripts/start-all.sh first"

"$SCRIPTS/sketch.sh"

mkdir -p "$RUN/logs"
status=0
podman exec r17-app python -m unittest -v tests.test_sketches >"$RUN/logs/tests.log" 2>&1 || status=$?
cat "$RUN/logs/tests.log"
[ "$status" = "0" ] || fail "tests failed, see .run/logs/tests.log"
log "all tests passed"
