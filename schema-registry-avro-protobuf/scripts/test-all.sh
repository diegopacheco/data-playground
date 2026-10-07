#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require podman
require curl
port_up "$(service_port ui)" || fail "ui is down, run scripts/start-all.sh first"
wait_until 60 api status || fail "app does not answer on $(service_url ui)"

mkdir -p "$RUN/logs"
status=0
podman exec r10-app python -m unittest -v tests.test_registry >"$RUN/logs/tests.log" 2>&1 || status=$?
cat "$RUN/logs/tests.log"
grep -q '^OK' "$RUN/logs/tests.log" || status=1
[ "$status" = "0" ] || fail "tests failed, see .run/logs/tests.log"
log "all tests passed"
