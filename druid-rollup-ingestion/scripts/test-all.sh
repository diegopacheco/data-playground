#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require curl
require python3
port_up "$(service_port ui)" || fail "ui is down, run scripts/start-all.sh first"

ORDERS="$ROOT/data/orders.csv"
API="$(service_url ui)/api"

check() {
  if [ "$2" = "$3" ]; then
    log "PASS $1"
  else
    printf "FAIL %s\nexpected:\n%s\nactual:\n%s\n" "$1" "$2" "$3" >&2
    exit 1
  fi
}

json() {
  python3 -c "import json,sys; d=json.load(sys.stdin); $1"
}

awk_events() {
  awk 'NR>1' "$ORDERS" | wc -l | tr -d ' '
}

awk_rollup_rows() {
  awk -F, 'NR>1{print substr($7,1,10) "|" $4 "|" $2}' "$ORDERS" | sort -u | wc -l | tr -d ' '
}

awk_days() {
  awk -F, 'NR>1{d=substr($7,1,10); raw[d]++; k=d "|" $4 "|" $2; if(!(k in seen)){seen[k]=1; roll[d]++}}
    END{for(d in raw) printf "%s 1 %d 1 %d\n", d, roll[d], raw[d]}' "$ORDERS" | sort
}

awk_categories() {
  awk -F, 'NR>1{c[$4]++;q[$4]+=$5;r[$4]+=$5*$6}END{for(k in c)printf "%s %d %d %.2f\n",k,c[k],q[k],r[k]}' "$ORDERS" | sort
}

summary="$(curl -sf "$API/summary")" || fail "GET /api/summary failed"
segments="$(curl -sf "$API/segments")" || fail "GET /api/segments failed"
categories="$(curl -sf "$API/categories")" || fail "GET /api/categories failed"

events="$(awk_events)"
rollup_rows="$(awk_rollup_rows)"
expected_ratio="$(python3 -c "print(round($events / $rollup_rows, 4))")"

check "raw datasource keeps one stored row per csv line" "$events" "$(printf "%s" "$summary" | json 'print(d["orders_raw"]["stored_rows"])')"
check "rollup datasource stores one row per day+category+customer" "$rollup_rows" "$(printf "%s" "$summary" | json 'print(d["orders_rollup"]["stored_rows"])')"
check "rollup count metric still sums back to every ingested event" "$events" "$(printf "%s" "$summary" | json 'print(d["orders_rollup"]["events"])')"
check "rollup ratio equals events over distinct day+category+customer" "$expected_ratio" "$(printf "%s" "$summary" | json 'print(d["rollup_ratio"])')"
check "COUNT(*) on the rollup datasource counts stored rows, not events" "$rollup_rows" "$(druid_value "SELECT COUNT(*) FROM orders_rollup")"
check "segmentGranularity DAY gives one segment per day with awk row counts" "$(awk_days)" "$(printf "%s" "$segments" | json 'print("\n".join("%s %d %d %d %d" % (x["day"], x["rollup_segments"], x["rollup_rows"], x["raw_segments"], x["raw_rows"]) for x in d))')"

format_categories() {
  json "print(\"\n\".join(\"%s %d %d %.2f\" % (r[\"category\"], r[\"orders\"], r[\"quantity\"], r[\"revenue\"]) for r in d[\"$1\"]))"
}

check "rollup per-category aggregates match awk" "$(awk_categories)" "$(printf "%s" "$categories" | format_categories rollup)"
check "raw per-category aggregates match awk" "$(awk_categories)" "$(printf "%s" "$categories" | format_categories raw)"
check "rollup and raw per-category aggregates are identical" "True" "$(printf "%s" "$categories" | json 'print(d["identical"])')"

log "events=$events rollup_rows=$rollup_rows ratio=$expected_ratio"
log "per category (category orders quantity revenue):"
awk_categories
log "all tests passed"
