#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require curl
require python3
port_up "$(service_port ui)" || fail "ui is down, run scripts/start-all.sh first"

log "dbt build with data tests"
compose run --rm p5-pipeline bash -c "cd dbt && dbt build" || fail "dbt build failed"

log "comparing /api/revenue with an independent awk calculation over data/orders.csv"
expected="$(awk -F, 'NR>1{c[$4]++;q[$4]+=$5;r[$4]+=$5*$6}END{for(k in c)printf "%s %d %d %.2f\n",k,c[k],q[k],r[k]}' "$ROOT/data/orders.csv" | sort)"
actual="$(curl -sf "$(service_url ui)/api/revenue" | python3 -c 'import json,sys
for r in json.load(sys.stdin): print("%s %d %d %.2f" % (r["category"], r["total_orders"], r["total_quantity"], r["total_revenue"]))' | sort)"

printf "%s\n" "$actual"
[ "$(printf "%s\n" "$actual" | wc -l | tr -d ' ')" = "6" ] || fail "expected 6 categories"
[ "$expected" = "$actual" ] || fail "api does not match csv, expected: $expected"
log "all tests passed"
