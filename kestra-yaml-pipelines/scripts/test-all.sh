#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require curl
require python3
port_up "$(service_port ui)" || fail "stack is not running, run ./scripts/start-all.sh first"
kestra_ready || fail "kestra is not reachable"

expected="$(awk -F, 'NR>1{o[$4]++; q[$4]+=$5; r[$4]+=$5*$6} END{for(c in o) printf "%s %d %d %.2f\n", c, o[c], q[c], r[c]}' "$ROOT/data/orders.csv" | sort)"
csv_rows="$(awk 'NR>1' "$ROOT/data/orders.csv" | wc -l | tr -d ' ')"

api_revenue() {
  curl -sf "$(service_url ui)/api/revenue" | python3 -c 'import json,sys; [print("%s %d %d %.2f" % (r["category"], r["total_orders"], r["total_quantity"], r["total_revenue"])) for r in json.load(sys.stdin)]' | sort
}

verify_revenue() {
  local actual
  actual="$(api_revenue)"
  log "expected from csv (awk)"
  log "$expected"
  log "actual from /api/revenue (postgres)"
  log "$actual"
  [ "$(printf "%s\n" "$actual" | wc -l | tr -d ' ')" = "6" ] || fail "expected 6 categories"
  [ "$expected" = "$actual" ] || fail "postgres result does not match csv aggregation"
}

verify_quality_row() {
  local row
  row="$("$SCRIPTS/sql-console.sh" -tA -F' ' -c "SELECT source_rows, loaded_orders, categories, bad_rows, passed FROM dq_results WHERE execution_id = '$1'" </dev/null)"
  log "dq_results for $1: $row"
  [ "$row" = "$2" ] || fail "dq_results for $1 was '$row', expected '$2'"
}

log "test 1: pipeline execution via API, flow trigger runs the quality check"
"$SCRIPTS/run-pipeline.sh"
read -r pipeline_id quality_id <"$RUN/last-run"
verify_revenue
verify_quality_row "$quality_id" "$csv_rows $csv_rows 6 0 t"

log "test 2: quality gate fails when loaded data no longer matches the source"
"$SCRIPTS/sql-console.sh" -q -c "UPDATE revenue_by_category SET total_orders = total_orders - 1 WHERE category = 'toys'" </dev/null >/dev/null
bad_id="$(kcurl -X POST -F "source_rows=$csv_rows" "$(kestra_api)/executions/$NAMESPACE/$QUALITY_FLOW" | json_field id)"
state="$(wait_final_state "$bad_id")"
log "quality execution $bad_id on corrupted table ended $state"
[ "$state" = "FAILED" ] || fail "quality gate should FAIL on corrupted data, got $state"
verify_quality_row "$bad_id" "$csv_rows $((csv_rows - 1)) 6 0 f"

log "test 3: rerunning the pipeline repairs the table (truncate and reload is idempotent)"
"$SCRIPTS/run-pipeline.sh"
verify_revenue

log "tests passed"
