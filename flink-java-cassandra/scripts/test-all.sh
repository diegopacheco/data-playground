#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

log "tests started"

require curl
require python3
url="$(service_url ui)/api/revenue"
port_up "$(service_port ui)" || fail "ui is not running, run ./scripts/start-all.sh first"

expected="$(awk -F, 'NR>1 && NF>=7 {o[$4]++; q[$4]+=$5; r[$4]+=$5*$6} END {for (c in o) printf "%s,%d,%d,%.2f\n", c, o[c], q[c], r[c]}' "$ROOT/data/orders.csv" | sort)"
actual="$(curl -fsS "$url" | python3 -c 'import json,sys; [print("%s,%d,%d,%.2f" % (r["category"], r["total_orders"], r["total_quantity"], r["total_revenue"])) for r in json.load(sys.stdin)]' | sort)"

log "expected from awk on data/orders.csv"
log "$expected"
log "actual from $url"
log "$actual"

[ "$(printf "%s\n" "$actual" | wc -l | tr -d ' ')" = "6" ] || fail "expected 6 categories"
[ "$expected" = "$actual" ] || fail "api results do not match the independent calculation"

log "tests passed"
