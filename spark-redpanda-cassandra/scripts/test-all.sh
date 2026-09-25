#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

log "tests started"

require curl
require python3
port_up "$(service_port ui)" || fail "ui is not running, run ./scripts/start-all.sh first"

"$SCRIPTS/pipeline.sh"

expected="$(tail -n +2 "$ROOT/data/orders.csv" | awk -F, '{o[$4]++; q[$4]+=$5; r[$4]+=$5*$6} END {for (c in o) printf "%s %d %d %.2f\n", c, o[c], q[c], r[c]}' | sort)"
actual="$(curl -sf "$(service_url ui)/api/revenue" | python3 -c 'import json,sys
for r in json.load(sys.stdin): print(r["category"], r["total_orders"], r["total_quantity"], "%.2f" % r["total_revenue"])' | sort)"

log "expected from csv"
log "$expected"
log "actual from api"
log "$actual"

[ "$(printf "%s\n" "$actual" | wc -l | tr -d ' ')" = "6" ] || fail "expected 6 categories"
[ "$expected" = "$actual" ] || fail "api result does not match csv aggregation"

log "tests passed"
