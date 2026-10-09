#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require curl
require python3
for name in $(service_names); do
  port_up "$(service_port "$name")" || fail "$name is down, run scripts/start-all.sh first"
done
wait_until 60 api status || fail "app does not answer on $(service_url ui)"

mkdir -p "$RUN/logs"
status=0
UI_URL="$(service_url ui)" S3_URL="$(service_url minio)" DATA_DIR="$ROOT/data" PYTHONPATH="$ROOT/app" \
  python3 -m unittest -v tests.test_lakehouse 2>&1 | tee "$RUN/logs/tests.log" || status=$?
grep -q '^OK' "$RUN/logs/tests.log" || status=1
[ "$status" = "0" ] || fail "lakehouse tests failed, see .run/logs/tests.log"
log "all tests passed"
