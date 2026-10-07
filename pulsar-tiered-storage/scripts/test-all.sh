#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require curl
require python3
require podman
port_up "$(service_port ui)" || fail "ui is down, run scripts/start-all.sh first"
wait_until 60 api cluster || fail "app does not answer on $(service_url ui)"

mkdir -p "$RUN/logs"
status=0
UI_URL="$(service_url ui)" BROKER_URL="http://localhost:$(service_port broker)" BOOKIE_URL="http://localhost:$(service_port bookie)" \
  S3_URL="http://localhost:$(service_port minio)" DATA_DIR="$ROOT/data" \
  python3 -m unittest -v tests.test_tiered_storage 2>&1 | tee "$RUN/logs/tests.log" || status=$?
grep -q '^OK' "$RUN/logs/tests.log" || status=1
[ "$status" = "0" ] || fail "tiered storage tests failed, see $RUN/logs/tests.log"
log "all tests passed"
