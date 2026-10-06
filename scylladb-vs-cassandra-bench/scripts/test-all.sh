#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require curl
require python3
[ -f "$RESULTS" ] || fail "results.json missing, run ./scripts/start-all.sh first"
[ -f "$BENCH_CSV" ] || fail "$BENCH_CSV missing, run BENCH_FORCE=1 ./scripts/start-all.sh"
port_up "$(service_port ui)" || fail "ui is not running, run ./scripts/start-all.sh first"

expected() {
  awk -F, 'NR>1 && NF>=7 {c=$4; o[c]++; q[c]+=$5; p[c]+=$6; if (!(c in mn) || $6+0<mn[c]) mn[c]=$6+0; if (!(c in mx) || $6+0>mx[c]) mx[c]=$6+0}
    END {for (c in o) printf "%s %d %d %.2f %.2f %.2f\n", c, o[c], q[c], p[c], mn[c], mx[c]}' "$BENCH_CSV" | sort
}

from_results() {
  python3 -c '
import json, sys
data = json.load(open(sys.argv[1]))
db = next(d for d in data["databases"] if d["name"] == sys.argv[2])
for a in sorted(db["aggregates"], key=lambda a: a["category"]):
    print("%s %d %d %.2f %.2f %.2f" % (a["category"], a["orders"], a["quantity"], a["price_sum"], a["min_price"], a["max_price"]))
' "$RESULTS" "$1"
}

from_live() {
  podman exec "$1" cqlsh --request-timeout=60 -e "SELECT category, count(*), sum(quantity), sum(price), min(price), max(price) FROM bench.orders GROUP BY category" |
    awk -F'|' 'NF==6 && $2 ~ /[0-9]/ {for (i=1;i<=6;i++) gsub(/ /,"",$i); printf "%s %d %d %.2f %.2f %.2f\n", $1, $2, $3, $4, $5, $6}' | sort
}

check() {
  local label got
  label="$1"
  got="$2"
  if [ "$got" = "$want" ]; then
    log "PASS $label"
  else
    log "got for $label"
    printf "%s\n" "$got"
    fail "$label does not match the awk totals of data/bench-orders.csv"
  fi
}

want="$(expected)"
log "expected per-category totals from awk over data/bench-orders.csv (category orders quantity price_sum min max)"
printf "%s\n" "$want"
[ "$(printf "%s\n" "$want" | wc -l | tr -d ' ')" -eq 6 ] || fail "expected 6 categories"

check "results.json scylladb aggregates" "$(from_results scylladb)"
check "results.json cassandra aggregates" "$(from_results cassandra)"
check "live scylladb GROUP BY" "$(from_live "$SCYLLA_CONTAINER")"
check "live cassandra GROUP BY" "$(from_live "$CASSANDRA_CONTAINER")"

python3 -c '
import json, sys
data = json.load(open(sys.argv[1]))
assert data["aggregates_match"] is True, "aggregates_match is false"
for d in data["databases"]:
    ops = {o["operation"]: o for o in d["operations"]}
    assert set(ops) == {"insert", "point_read", "aggregate"}, d["name"] + " missing operations"
    assert ops["insert"]["ops"] == data["setup"]["rows"], d["name"] + " insert count differs from rows"
    for o in ops.values():
        assert o["errors"] == 0, "%s %s had %d errors" % (d["name"], o["operation"], o["errors"])
        assert 0 < o["p50_ms"] <= o["p95_ms"] <= o["p99_ms"] <= o["max_ms"], "%s %s percentiles out of order" % (d["name"], o["operation"])
        assert o["throughput"] > 0
' "$RESULTS" || fail "results.json sanity checks failed"
log "PASS results.json sanity (no errors, ordered percentiles, all rows inserted)"

curl -fsS "$(service_url ui)/api/results" | python3 -c 'import json,sys; json.load(sys.stdin)' || fail "/api/results is not valid json"
curl -fsS "$(service_url ui)/" | grep -q "ScyllaDB vs Cassandra" || fail "ui page not served"
log "PASS ui and api"
log "ALL PASS"
