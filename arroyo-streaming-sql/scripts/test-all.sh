#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

log "tests started"

require curl
require python3
port_up "$(service_port ui)" || fail "ui is not running, run ./scripts/start-all.sh first"

expected_for() {
  tail -n +2 "$ROOT/data/orders.csv" | awk -F, -v n="$1" '{o[$4]+=n; q[$4]+=$5*n; r[$4]+=$5*$6*n} END {for (c in o) printf "%s %d %d %.2f\n", c, o[c], q[c], r[c]}' | sort
}

actual_from_api() {
  curl -sf "$(service_url ui)/api/revenue" | json_get 'for r in d["categories"]: print(r["category"], r["total_orders"], r["total_quantity"], "%.2f" % r["total_revenue"])' | sort
}

api_matches() {
  [ "$(actual_from_api)" = "$1" ]
}

check() {
  local expected actual
  expected="$(expected_for "$1")"
  wait_until 60 api_matches "$expected" || true
  actual="$(actual_from_api)"
  log "expected from csv x$1"
  log "$expected"
  log "actual from api"
  log "$actual"
  [ "$(printf "%s\n" "$actual" | wc -l | tr -d ' ')" = "6" ] || fail "expected 6 categories"
  [ "$expected" = "$actual" ] || fail "api result does not match csv aggregation x$1"
}

"$SCRIPTS/pipeline.sh"
check 1

log "producing the same orders again, the running aggregate must double"
produce_orders >"$LOGS/produce-again.log" || fail "produce failed"
check 2

log "tests passed"
