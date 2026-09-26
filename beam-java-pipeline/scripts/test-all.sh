#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require curl
require python3
podman image exists "$BUILD_IMAGE" || fail "build image missing, run ./scripts/setup.sh first"
port_up "$(service_port ui)" || fail "ui is down, run ./scripts/start-all.sh first"

log "beam unit tests with TestPipeline and PAssert"
podman run --rm --memory 768m "$BUILD_IMAGE" mvn -B -o test >"$LOGS/unit-tests.log" 2>&1 || { tail -40 "$LOGS/unit-tests.log" >&2; fail "beam unit tests failed"; }
grep -E "Tests run:.*Fail" "$LOGS/unit-tests.log" | tail -1
grep -q "BUILD SUCCESS" "$LOGS/unit-tests.log" || fail "maven did not report BUILD SUCCESS"

log "rerunning the pipeline to prove the upsert is idempotent"
"$SCRIPTS/pipeline.sh"
rows="$(psql_exec -tAc "SELECT count(*) FROM revenue_by_category")"
[ "$rows" = "6" ] || fail "expected 6 rows in revenue_by_category after rerun, got $rows"

log "comparing /api/revenue with an independent awk calculation over data/orders.csv"
expected="$(awk -F, 'NR>1{c[$4]++;q[$4]+=$5;r[$4]+=$5*$6}END{for(k in c)printf "%s %d %d %.2f\n",k,c[k],q[k],r[k]}' "$ROOT/data/orders.csv" | sort)"
actual="$(curl -sf "$(service_url ui)/api/revenue" | python3 -c 'import json,sys
for r in json.load(sys.stdin): print("%s %d %d %.2f" % (r["category"], r["total_orders"], r["total_quantity"], r["total_revenue"]))' | sort)"

log "expected from csv"
log "$expected"
log "actual from api"
log "$actual"

[ "$(printf "%s\n" "$actual" | wc -l | tr -d ' ')" = "6" ] || fail "expected 6 categories"
[ "$expected" = "$actual" ] || fail "api result does not match csv aggregation"
log "all tests passed"
