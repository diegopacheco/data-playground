#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

BATCH1="$ROOT/data/orders.csv"
BATCH2="$ROOT/data/orders-updates.csv"
REVENUE_SQL="SELECT category, orders, units, revenue FROM revenue_by_category ORDER BY category"

latest_orders() {
  awk -F, 'FNR>1 && NF>=7 {r[$1]=$0} END {for (k in r) print r[k]}' "$@"
}

aggregate() {
  awk -F, '{o[$4]++; q[$4]+=$5; r[$4]+=$5*$6} END {for (c in o) printf "%s,%d,%d,%.2f\n", c, o[c], q[c], r[c]}' | sort
}

wait_match() {
  local expected actual deadline
  expected="$1"
  deadline=$((SECONDS + 60))
  actual=""
  while [ "$SECONDS" -lt "$deadline" ]; do
    actual="$(sql "$REVENUE_SQL" || true)"
    if [ "$actual" = "$expected" ]; then
      printf "%s\n" "$actual"
      return 0
    fi
    sleep 1
  done
  printf "expected:\n%s\nactual:\n%s\n" "$expected" "$actual" >&2
  return 1
}

port_up "$(service_port kafka)" || fail "kafka is down, run scripts/start-all.sh first"
port_up "$(service_port ui)" || fail "ui is down, run scripts/start-all.sh first"

log "resetting lakehouse and topic"
stop_bg pipeline
delete_topic
rm -rf "$WAREHOUSE"
mkdir -p "$WAREHOUSE"
create_topic
start_pipeline

log "test 1: first batch lands in orders and revenue_by_category"
produce "$BATCH1"
expected1="$(latest_orders "$BATCH1" | aggregate)"
wait_match "$expected1" || fail "revenue_by_category does not match awk after batch 1"
count="$(sql "SELECT COUNT(*) FROM orders")"
[ "$count" = "$(latest_orders "$BATCH1" | wc -l | tr -d ' ')" ] || fail "orders count $count does not match batch 1"
log "PASS batch 1: $count orders, aggregation matches awk"

log "test 2: updates retract old values and move revenue between categories"
produce "$BATCH2"
expected2="$(latest_orders "$BATCH1" "$BATCH2" | aggregate)"
wait_match "$expected2" || fail "revenue_by_category does not match awk after batch 2"
count="$(sql "SELECT COUNT(*) FROM orders")"
[ "$count" = "$(latest_orders "$BATCH1" "$BATCH2" | wc -l | tr -d ' ')" ] || fail "orders count $count does not match batch 1 + batch 2"
log "PASS batch 2: $count orders, aggregation matches awk"

log "test 3: changed categories between batches"
diff <(printf "%s\n" "$expected1") <(printf "%s\n" "$expected2") | grep '^[<>]' || true

log "test 4: order 1006 moved from toys to sports"
row="$(sql "SELECT order_id, category, quantity, price FROM orders WHERE order_id = 1006")"
[ "$row" = "1006,sports,1,12.32" ] || fail "order 1006 is $row"
log "PASS $row"

log "test 5: ui api answers"
api="$(service_url ui)/api"
curl -sf "$api/revenue" | grep -q '"category":"sports"' || fail "$api/revenue failed"
curl -sf "$api/summary" | grep -q "\"orders\":$count" || fail "$api/summary failed"
curl -sf "$api/snapshots" | grep -q '"kind":"APPEND"' || fail "$api/snapshots failed"
log "PASS api"

log "all tests passed"
