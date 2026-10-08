#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

log "unit tests"
"$VENV/bin/python" -m unittest discover -s "$ROOT/tests" || fail "unit tests failed"

port_up "$UI_PORT" || fail "stack is not running, run ./scripts/start-all.sh first"

run_id() {
  printf "%s\n" "$1" | sed -n 's/.*UUID: \([0-9a-f-]*\).*/\1/p' | head -1
}

log "clearing the result cache so run 1 has to compute transform"
rm -rf "$PREFECT_LOCAL_STORAGE_PATH"

log "run 1 via prefect deployment run $DEPLOYMENT"
first="$(run_id "$("$SCRIPTS/run-flow.sh")")"
[ -n "$first" ] || fail "no flow run id for run 1"
"$VENV/bin/python" "$ROOT/tests/check_run.py" "$(service_url ui)" "$first" extract=Completed:2 transform=Completed:1 load=Completed:1 || fail "run 1 states wrong"
grep -q "attempt 1: marker $first.extract missing" "$LOGS/serve.log" || fail "run 1 extract did not fail on attempt 1"

log "run 2 via prefect deployment run $DEPLOYMENT"
second="$(run_id "$("$SCRIPTS/run-flow.sh")")"
[ -n "$second" ] || fail "no flow run id for run 2"
"$VENV/bin/python" "$ROOT/tests/check_run.py" "$(service_url ui)" "$second" extract=Completed:2 transform=Cached:1 load=Completed:1 || fail "run 2 transform was not cached"

log "serve.log lines for this test"
sed -n "/$first/,\$p" "$LOGS/serve.log" | grep -E "Task run '(extract|transform)" | sed 's/^/  /'

expected="$(awk -F, 'NR>1{o[$4]++; q[$4]+=$5; r[$4]+=$5*$6} END{for(c in o) printf "%s %d %d %.2f\n", c, o[c], q[c], r[c]}' "$ROOT/data/orders.csv" | sort)"
actual="$(printf "SELECT category, orders, units, revenue FROM revenue_by_category ORDER BY category;\n" | "$SCRIPTS/sql-console.sh" -At -F ' ' | sort)"

log "expected from csv (awk)"
printf "%s\n" "$expected" | sed 's/^/  /'
log "actual from postgres revenue_by_category"
printf "%s\n" "$actual" | sed 's/^/  /'

[ "$(printf "%s\n" "$actual" | wc -l | tr -d ' ')" = "6" ] || fail "expected 6 categories"
[ "$expected" = "$actual" ] || fail "postgres result does not match csv aggregation"

log "tests passed"
