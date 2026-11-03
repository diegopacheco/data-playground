#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

log "tests started"

require curl
require python3
port_up "$(service_port ui)" || fail "ui is not running, run ./scripts/start-all.sh first"
catalog_ready || fail "iceberg rest catalog is not running, run ./scripts/start-all.sh first"

api="$(service_url ui)/api"
checker="$ROOT/check/medallion_check.py"

check() {
  if [ "$2" = "$3" ]; then
    log "PASS $1"
  else
    printf "FAIL %s\nexpected:\n%s\nactual:\n%s\n" "$1" "$2" "$3" >&2
    exit 1
  fi
}

lake_state() {
  python3 "$checker" actual "$api" || fail "could not read lake state from $api"
}

first_run="$(lake_state)"

log "re-running the pipeline on the same landing files"
run_lake_job >"$LOGS/lake-job-rerun.log"
grep -q "no new files, bronze unchanged" "$LOGS/lake-job-rerun.log" || fail "re-run ingested files again, see $LOGS/lake-job-rerun.log"
log "PASS re-run skipped already ingested files"
check "re-run leaves bronze, silver, quarantine and gold unchanged" "$first_run" "$(lake_state)"

log "rebuilding every layer from scratch"
run_lake_job reset >"$LOGS/lake-job-reset.log"
check "full rebuild gives the same layers as the incremental runs" "$first_run" "$(lake_state)"

expected="$(python3 "$checker" expected "$LANDING_DIR")"
log "independent python computation"
log "$expected"
check "lake matches independent python cleaning rules" "$expected" "$(lake_state)"

log "tests passed"
