#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require curl
require python3
for name in $(service_names); do
  port_up "$(service_port "$name")" || fail "$name is down, run scripts/start-all.sh first"
done

MARQUEZ_API="$(service_url marquez)/api/v1"
JOB_NAMES="load_raw_orders build_clean_orders build_revenue_by_category"

check() {
  if [ "$2" = "$3" ]; then
    log "PASS $1"
  else
    printf "FAIL %s\nexpected: %s\nactual:   %s\n" "$1" "$2" "$3" >&2
    exit 1
  fi
}

json() {
  python3 -c "import json,sys; d=json.load(sys.stdin); print($1)"
}

run_counts() {
  for job in $JOB_NAMES; do
    printf "%s=%s " "$job" "$(curl -sf "$MARQUEZ_API/namespaces/$JOB_NAMESPACE/jobs/$job/runs?limit=1000" | json 'len(d["runs"])')"
  done
}

expected_counts() {
  for pair in $1; do
    printf "%s=%s " "${pair%%=*}" "$((${pair##*=} + 1))"
  done
}

dataset_names() {
  curl -sf "$MARQUEZ_API/namespaces/$METALAKE/datasets?limit=100" | json '" ".join(sorted(x["name"] for x in d["datasets"]))'
}

before="$(run_counts)"
datasets_before="$(dataset_names)"
log "runs before: $before"
"$SCRIPTS/pipeline.sh"
after="$(run_counts)"
log "runs after:  $after"
check "a rerun adds exactly one run per job" "$(expected_counts "$before")" "$after"
check "a rerun does not duplicate datasets in marquez" "$datasets_before" "$(dataset_names)"
check "marquez namespace $METALAKE holds the three tables" "shop_pg.clean.clean_orders shop_pg.gold.revenue_by_category shop_pg.raw.raw_orders" "$(dataset_names)"

for job in $JOB_NAMES; do
  run_id="$(curl -sf "$MARQUEZ_API/namespaces/$JOB_NAMESPACE/jobs/$job/runs?limit=1" | json 'd["runs"][0]["id"]')"
  seen="$(podman exec r6-gravitino grep -c "$run_id" logs/gravitino_lineage.log || true)"
  check "latest $job run reached marquez through the gravitino lineage endpoint (START and COMPLETE in its lineage log)" "2" "$seen"
done

check "raw, clean and gold tables in postgres were created by gravitino" "3" \
  "$(psql_value "select count(*) from pg_class c join pg_namespace n on n.oid = c.relnamespace where n.nspname in ('raw','clean','gold') and c.relkind = 'r' and obj_description(c.oid, 'pg_class') like '%From Gravitino%'")"
check "raw_orders holds every csv row" "$(awk 'NR>1 && NF' "$ROOT/data/orders.csv" | wc -l | tr -d ' ')" "$(psql_value "select count(*) from raw.raw_orders")"
check "clean_orders holds no customer names, only 64 char sha256 hashes" "0" \
  "$(psql_value "select count(*) from clean.clean_orders where customer_hash !~ '^[0-9a-f]{64}$'")"

mkdir -p "$RUN/logs"
status=0
GRAVITINO_URL="$(service_url gravitino)" MARQUEZ_URL="$(service_url marquez)" UI_URL="$(service_url ui)" \
  python3 -m unittest -v tests.test_governance >"$RUN/logs/tests.log" 2>&1 || status=$?
cat "$RUN/logs/tests.log"
[ "$status" = "0" ] || fail "governance and lineage tests failed"
log "all tests passed"
