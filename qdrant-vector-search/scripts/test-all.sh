#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require curl
require python3
port_up "$(service_port qdrant)" || fail "qdrant is down, run scripts/start-all.sh first"
port_up "$(service_port ui)" || fail "ui is down, run scripts/start-all.sh first"

rows="$(csv_rows)"
before="$(point_count)"
log "csv rows (awk): $rows, qdrant points: $before"
[ "$rows" = "$before" ] || fail "point count $before differs from csv rows $rows"

log "rerunning the pipeline to prove upserts are idempotent"
"$SCRIPTS/pipeline.sh"
after="$(point_count)"
[ "$after" = "$rows" ] || fail "after a second pipeline run qdrant has $after points, expected $rows"
log "points after second run: $after"

mkdir -p "$RUN/logs"
status=0
QDRANT_URL="$(service_url qdrant)" UI_URL="$(service_url ui)" python3 -m unittest -v tests.test_search >"$RUN/logs/tests.log" 2>&1 || status=$?
cat "$RUN/logs/tests.log"
[ "$status" = "0" ] || fail "search tests failed"
log "all tests passed"
