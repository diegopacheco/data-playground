#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require curl
require python3
require podman-compose
port_up "$(service_port ui)" || fail "ui is down, run scripts/start-all.sh first"

rows="$(csv_rows)"
before="$(ui_rows)"
log "csv rows (awk): $rows, parquet rows: $before"
[ "$rows" = "$before" ] || fail "parquet has $before rows, csv has $rows"

log "rerunning the pipeline to prove the parquet output is overwritten, not appended"
"$SCRIPTS/pipeline.sh"
after="$(ui_rows)"
[ "$after" = "$rows" ] || fail "after a second pipeline run parquet has $after rows, expected $rows"
log "parquet rows after second run: $after"

mkdir -p "$RUN/logs"
status=0
compose run --rm r5-tests >"$RUN/logs/tests.log" 2>&1 || status=$?
grep -v 'level=warning' "$RUN/logs/tests.log" || true
[ "$status" = "0" ] || fail "tests failed, see $RUN/logs/tests.log"
grep -q '^OK' "$RUN/logs/tests.log" || fail "unittest did not report OK, see $RUN/logs/tests.log"
log "all tests passed"
