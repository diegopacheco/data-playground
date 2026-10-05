#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require curl
port_up "$(service_port ui)" || fail "ui is not running, run ./scripts/start-all.sh first"
API="$(service_url ui)/api"

expected() {
  awk -F, 'NR>1 && NF>=7 {o[$4]++; c[$4]+=$5*int($6*100+0.5)} END {for (k in o) printf "%s %d %d\n", k, o[k], c[k]}' "$ROOT/data/orders.csv" | sort
}

rows() {
  curl -fsS "$API/$1" | tr -d '[]' | sed 's/},{/}|{/g' | tr '|' '\n' | sed '/^$/d'
}

categories() {
  rows categories | sed -E 's/.*"category":"([^"]*)".*"orders":([0-9]+),"credits_cents":([0-9]+).*/\1 \2 \3/' | sort
}

customers_total() {
  rows customers | sed -E 's/.*"debits_cents":([0-9]+).*/\1/' | awk '{s+=$1} END {print s+0}'
}

want="$(expected)"
got="$(categories)"
log "expected from data/orders.csv (category orders cents)"
printf "%s\n" "$want"
log "actual category account balances from tigerbeetle"
printf "%s\n" "$got"
[ "$got" = "$want" ] || fail "category balances do not match awk revenue in cents"
[ "$(printf "%s\n" "$got" | wc -l | tr -d ' ')" -eq 6 ] || fail "expected 6 category accounts"

total="$(printf "%s\n" "$want" | awk '{s+=$3} END {print s+0}')"
debits="$(customers_total)"
log "customer debits $debits, category credits $total"
[ "$debits" = "$total" ] || fail "customer debits do not balance category credits"

log "re-ingesting to prove transfers are idempotent"
run_java ledger.Ingest >"$LOGS/reingest.log" 2>&1 || fail "re-ingest failed, see $LOGS/reingest.log"
orders="$(awk -F, 'NR>1 && NF>=7' "$ROOT/data/orders.csv" | wc -l | tr -d ' ')"
grep -q "transfers: 0 created, $orders already existed" "$LOGS/reingest.log" || fail "re-ingest created new transfers"
[ "$(categories)" = "$want" ] || fail "balances changed after re-ingest"

bench="$(curl -fsS "$API/bench")"
log "throughput run $bench"
printf "%s" "$bench" | grep -q '"verified":true' || fail "throughput run missing or not verified"

curl -fsS "$(service_url ui)/" | grep -q "<svg" || fail "ui page not served"
log "PASS"
