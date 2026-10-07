#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

port_up "$(service_port thrift)" || fail "thrift is down, run ./scripts/start-all.sh first"
port_up "$(service_port ui)" || fail "ui is down, run ./scripts/start-all.sh first"

CSV="$ROOT/data/orders.csv"
CUT_ISO="$(printf "%s" "$CUTOFF" | tr ' ' 'T')Z"

api() {
  curl -sf "$(service_url ui)/api/$1" | "$VENV/bin/python" -c "$2"
}

log "dbt test: schema and singular data tests"
dbt test || fail "dbt test failed"

log "revenue_by_category vs awk over data/orders.csv"
expected="$(awk -F, 'NR>1{c[$4]++;q[$4]+=$5;r[$4]+=$5*$6}END{for(k in c)printf "%s %d %d %.2f\n",k,c[k],q[k],r[k]}' "$CSV" | sort)"
actual="$(api revenue 'import json,sys
for r in json.load(sys.stdin): print("%s %d %d %.2f" % (r["category"], r["total_orders"], r["total_quantity"], r["total_revenue"]))' | sort)"
printf "%s\n" "$actual"
[ "$(printf "%s\n" "$actual" | wc -l | tr -d ' ')" = "6" ] || fail "expected 6 categories"
[ "$expected" = "$actual" ] || fail "revenue does not match csv, expected: $expected"

log "fct_orders snapshots: run 1 holds orders up to the cutoff, run 2 holds every order"
first_total="$(awk -F, -v c="$CUT_ISO" 'NR>1 && $7<=c{n++}END{print n}' "$CSV")"
all_total="$(awk 'NR>1{n++}END{print n}' "$CSV")"
snap="$(api snapshots 'import json,sys
print(" ".join(s["total_records"] for s in json.load(sys.stdin)))')"
log "snapshot total-records: $snap, awk expects: $first_total $all_total"
[ "$snap" = "$first_total $all_total" ] || fail "snapshots do not match run 1 and run 2 totals"

log "fct_orders merge: the overlap order is updated, not duplicated"
kept="$(awk -F, -v c="$CUT_ISO" 'NR>1 && $7<c{n++}END{print n}' "$CSV")"
merged="$(awk -F, -v c="$CUT_ISO" 'NR>1 && $7>=c{n++}END{print n}' "$CSV")"
loads="$(api loads 'import json,sys
print(" ".join(str(l["orders"]) for l in json.load(sys.stdin)))')"
log "rows per loaded_at: $loads, awk expects: $kept $merged"
[ "$loads" = "$kept $merged" ] || fail "merge did not keep run 1 rows and upsert run 2 rows"

log "all tests passed"
