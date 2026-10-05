#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

http_ok "$(service_url dagster)/server_info" || fail "dagster is not running, run scripts/start-all.sh first"
http_ok "$(service_url ui)/" || fail "results ui is not running, run scripts/start-all.sh first"

log "unit tests"
podman exec "$DAGSTER_CONTAINER" python -m pytest -q -p no:cacheprovider tests || fail "unit tests failed"

log "materializing raw_orders -> clean_orders -> revenue_by_category"
podman exec "$DAGSTER_CONTAINER" dagster asset materialize --select '*' -m "$DEFS_MODULE" >"$LOGS/materialize.log" 2>&1 || fail "materialization failed, see $LOGS/materialize.log"

podman exec "$DAGSTER_CONTAINER" python -m i36_pipeline.latest_run >"$RUN/latest_run.txt" 2>/dev/null || fail "could not read the latest dagster run"
cat "$RUN/latest_run.txt"
grep -q '^run .* SUCCESS$' "$RUN/latest_run.txt" || fail "dagster run did not succeed"
[ "$(grep -c '^materialized ' "$RUN/latest_run.txt")" -eq 3 ] || fail "expected 3 materialized assets"
[ "$(grep -c '^check .* PASSED$' "$RUN/latest_run.txt")" -eq 2 ] || fail "expected 2 passing asset checks"

expected="$RUN/expected.txt"
actual="$RUN/actual.txt"
awk -F, 'NR>1 && $5>0 && $6>0 && !seen[$1]++ {o[$4]++; u[$4]+=$5; r[$4]+=$5*$6} END {for (c in o) printf "%s %d %d %.2f\n", c, o[c], u[c], r[c]}' "$ROOT/data/orders.csv" | sort >"$expected"
curl -sf "$(service_url ui)/api/revenue" | python3 -c 'import json,sys; [print("%s %d %d %.2f" % (r["category"], r["orders"], r["units"], r["revenue"])) for r in json.load(sys.stdin)["rows"]]' | sort >"$actual"

log "awk (from csv)            | iceberg (via api)"
paste -d'|' "$expected" "$actual" | awk -F'|' '{printf "%-26s | %s\n", $1, $2}'
diff "$expected" "$actual" >/dev/null || fail "iceberg revenue does not match awk"
log "iceberg revenue matches awk"
