#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

clickhouse_ready >/dev/null 2>&1 || fail "clickhouse is not running, run ./scripts/start-all.sh first"
port_up "$(service_port ui)" || fail "ui is not running, run ./scripts/start-all.sh first"

normalize() {
  awk '{printf "%s %d %d %.2f\n", $1, $2, $3, $4}' | sort
}

expected() {
  awk -F, 'NR>1 && NF>=7 {o[$4]++; q[$4]+=$5; r[$4]+=$5*$6} END {for (c in o) print c, o[c], q[c], r[c]}' "$CSV" | normalize
}

summing_table() {
  ch -q "SELECT category, sum(total_orders), sum(total_quantity), sum(total_revenue) FROM sales.category_totals GROUP BY category FORMAT TSV" | normalize
}

merge_tree_table() {
  ch -q "SELECT category, count(), sum(quantity), sum(quantity * price) FROM sales.orders GROUP BY category FORMAT TSV" | normalize
}

api_totals() {
  "$PYTHON" -c 'import json,sys,urllib.request
for r in json.load(urllib.request.urlopen(sys.argv[1])): print(r["category"], r["orders"], r["quantity"], r["revenue"])' "$(service_url ui)/api/totals" | normalize
}

failures=0
check() {
  local name actual
  name="$1"
  actual="$("$2")"
  if [ "$actual" = "$EXPECTED" ]; then
    log "PASS $name matches awk"
  else
    printf "FAIL %s differs from awk\n" "$name" >&2
    diff <(printf "%s\n" "$EXPECTED") <(printf "%s\n" "$actual") >&2 || true
    failures=$((failures + 1))
  fi
}

EXPECTED="$(expected)"
printf "%s\n" "$EXPECTED"

rows="$(csv_rows)"
count="$(ingested_orders)"
distinct="$(ch -q "SELECT uniqExact(order_id) FROM sales.orders")"
if [ "$count" = "$rows" ] && [ "$distinct" = "$rows" ]; then
  log "PASS sales.orders holds $count rows, $distinct distinct order ids, csv has $rows"
else
  printf "FAIL sales.orders holds %s rows, %s distinct, csv has %s\n" "$count" "$distinct" "$rows" >&2
  failures=$((failures + 1))
fi

check "sales.category_totals (SummingMergeTree via kafka mv)" summing_table
check "sales.orders (MergeTree via kafka mv)" merge_tree_table
check "GET /api/totals" api_totals

[ "$failures" -eq 0 ] || fail "$failures check(s) failed"
log "all checks passed"
