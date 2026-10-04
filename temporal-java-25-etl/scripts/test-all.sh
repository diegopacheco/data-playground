#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

log "tests started"

require curl
require python3
port_up "$(service_port ui)" || fail "ui is not running, run ./scripts/start-all.sh first"
[ -n "$(bg_pid worker)" ] || fail "worker is not running, run ./scripts/start-all.sh first"

stamp="$(date +%Y%m%d-%H%M%S)"
retry_id="etl-retry-$stamp"
crash_id="etl-crash-$stamp"
api="$(service_url ui)/api"

check_history() {
  curl -fsS "$api/workflow?id=$1" | python3 "$SCRIPTS/check_history.py" "$2"
}

log "scenario 1: extractOrders fails on attempts 1 and 2, retry policy succeeds on attempt 3"
"$SCRIPTS/etl.sh" 2 5 "$retry_id"
check_history "$retry_id" retry || fail "retry scenario history check failed"

log "scenario 2: worker killed with SIGKILL during the heartbeating transformAggregate"
"$SCRIPTS/crash-recovery.sh" "$crash_id"
check_history "$crash_id" crash || fail "crash scenario history check failed"

log "scenario 3: postgres revenue_by_category matches an independent awk calculation"
expected="$(awk -F, 'NR>1 && NF>=7 {o[$4]++; q[$4]+=$5; r[$4]+=$5*$6} END {for (c in o) printf "%s,%d,%d,%.2f\n", c, o[c], q[c], r[c]}' "$ORDERS_CSV" | sort)"
actual="$(psql_exec -At -F, -c "SELECT category, total_orders, total_quantity, total_revenue FROM revenue_by_category ORDER BY category" | sort)"
api_rows="$(curl -fsS "$api/revenue" | python3 -c 'import json,sys; [print("%s,%d,%d,%.2f" % (r["category"], r["total_orders"], r["total_quantity"], r["total_revenue"])) for r in json.load(sys.stdin)]' | sort)"
owner="$(psql_exec -At -c "SELECT DISTINCT workflow_id FROM revenue_by_category")"

log "expected from awk on data/orders.csv"
log "$expected"
log "actual from postgres"
log "$actual"

[ "$(printf "%s\n" "$actual" | wc -l | tr -d ' ')" = "6" ] || fail "expected 6 categories"
[ "$expected" = "$actual" ] || fail "postgres results do not match the awk calculation"
[ "$expected" = "$api_rows" ] || fail "api results do not match the awk calculation"
[ "$owner" = "$crash_id" ] || fail "rows were last written by $owner, expected $crash_id"

log "tests passed"
