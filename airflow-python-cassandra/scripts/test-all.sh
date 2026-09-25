#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require python3
log "unit tests"
python3 -m unittest discover -s "$ROOT/tests" || fail "unit tests failed"

port_up "$(service_port ui)" || fail "stack is not running, run ./scripts/start-all.sh first"

log "end to end"
"$SCRIPTS/run-pipeline.sh"

expected="$(awk -F, 'NR>1{o[$4]++; q[$4]+=$5; r[$4]+=$5*$6} END{for(c in o) printf "%s %d %d %.2f\n", c, o[c], q[c], r[c]}' "$ROOT/data/orders.csv" | sort)"
actual="$(curl -sf "$(service_url ui)/api/revenue" | python3 -c 'import json,sys; [print("%s %d %d %.2f" % (r["category"], r["total_orders"], r["total_quantity"], r["total_revenue"])) for r in json.load(sys.stdin)]' | sort)"

log "expected from csv (awk)"
log "$expected"
log "actual from /api/revenue"
log "$actual"

[ "$(printf "%s\n" "$actual" | wc -l | tr -d ' ')" = "6" ] || fail "expected 6 categories"
[ "$expected" = "$actual" ] || fail "api result does not match csv aggregation"

log "tests passed"
