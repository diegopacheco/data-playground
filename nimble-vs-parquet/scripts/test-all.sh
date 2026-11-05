#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require podman-compose
require python3
port_up "$(service_port ui)" || fail "ui is down, run scripts/start-all.sh first"
mkdir -p "$RUN/logs"

log "format, dataset and results tests inside t9-bench"
status=0
compose run --rm -e NO_COLOR=1 -e PYTHONPATH=/bench/tests t9-bench python -m unittest -v test_formats >"$RUN/logs/tests.log" 2>&1 || status=$?
grep -v 'level=warning' "$RUN/logs/tests.log" || true
[ "$status" = "0" ] || fail "format tests failed, see .run/logs/tests.log"

log "api tests against $(service_url ui)"
status=0
UI_URL="$(service_url ui)" python3 -m unittest -v tests.test_api >"$RUN/logs/api.log" 2>&1 || status=$?
cat "$RUN/logs/api.log"
[ "$status" = "0" ] || fail "api tests failed"
log "all tests passed"
