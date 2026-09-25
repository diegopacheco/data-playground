#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

log "tests started"
url="$(service_url ui)/api/revenue"
body="$(curl -sf "$url")" || fail "could not reach $url, run ./scripts/start-all.sh first"

expected="$(awk -F, 'NR>1 { o[$4]++; q[$4]+=$5; r[$4]+=$5*$6 } END { for (c in o) printf "%s %d %d %.2f\n", c, o[c], q[c], r[c] }' "$ROOT/data/orders.csv" | sort)"
actual="$(printf "%s" "$body" | tr '{' '\n' | grep category | sed -E 's/.*"category":"([^"]+)","total_orders":([0-9]+),"total_quantity":([0-9]+),"total_revenue":([0-9.]+).*/\1 \2 \3 \4/' | awk '{ printf "%s %d %d %.2f\n", $1, $2, $3, $4 }' | sort)"

log "expected from data/orders.csv"
log "$expected"
log "actual from $url"
log "$actual"

[ "$(printf "%s\n" "$actual" | wc -l | tr -d ' ')" = "6" ] || fail "expected 6 categories"
[ "$expected" = "$actual" ] || fail "api totals do not match the csv totals"

curl -sf "$(service_url ui)/" | grep -q "<svg" || fail "ui page is not served at /"

log "tests passed"
