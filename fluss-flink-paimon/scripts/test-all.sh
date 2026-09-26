#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require curl
require python3
port_up "$(service_port ui)" || fail "ui is down, run scripts/start-all.sh first"
wait_until 60 api status || fail "app does not answer on $(service_url ui)"

mkdir -p "$RUN/logs"
status=0
UI_URL="$(service_url ui)" FLINK_URL="$(service_url flink)" DATA_DIR="$ROOT/data" \
  python3 -m unittest -v tests.test_lakehouse 2>&1 | tee "$RUN/logs/tests.log" || status=$?
grep -q '^OK' "$RUN/logs/tests.log" || status=1
[ "$status" = "0" ] || fail "lakehouse tests failed, see $RUN/logs/tests.log"
log "all tests passed"
