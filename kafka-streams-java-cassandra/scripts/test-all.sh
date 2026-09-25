#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require curl
port_up "$(service_port ui)" || fail "ui is not running, run ./scripts/start-all.sh first"

expected() {
  awk -F, 'NR>1 && NF>=7 {o[$4]++; q[$4]+=$5; r[$4]+=$5*$6} END {for (c in o) printf "%s %d %d %.2f\n", c, o[c], q[c], r[c]}' "$ROOT/data/orders.csv" | sort
}

actual() {
  curl -fsS "$(service_url ui)/api/revenue" | tr -d '[]' | sed 's/},{/}|{/g' | tr '|' '\n' |
    sed -E 's/.*"category":"([^"]*)","total_orders":([0-9]+),"total_quantity":([0-9]+),"total_revenue":([0-9.]+).*/\1 \2 \3 \4/' | sed '/^$/d' | sort
}

want="$(expected)"
tries=60
got=""
while [ "$tries" -gt 0 ]; do
  got="$(actual || true)"
  if [ "$got" = "$want" ]; then break; fi
  sleep 1
  tries=$((tries - 1))
done

log "expected from data/orders.csv"
printf "%s\n" "$want"
log "actual from $(service_url ui)/api/revenue"
printf "%s\n" "$got"

[ "$got" = "$want" ] || fail "api totals do not match the csv"
[ "$(printf "%s\n" "$got" | wc -l | tr -d ' ')" -eq 6 ] || fail "expected 6 categories"
curl -fsS "$(service_url ui)/" | grep -q "<svg" || fail "ui page not served"
log "PASS"
