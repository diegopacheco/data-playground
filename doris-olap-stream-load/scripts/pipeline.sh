#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require curl
require python3
wait_for 60 be_alive || fail "doris backend is not alive, run ./scripts/start-all.sh first"

mv_ready() {
  doris_sql -e "SHOW ALTER TABLE MATERIALIZED VIEW FROM sales" | grep mv_revenue_by_category | grep -q FINISHED
}

mv_exists() {
  doris_sql -e "DESC sales.orders ALL" | awk -F'\t' '{print $1}' | grep -qx mv_revenue_by_category
}

log "applying doris/schema.sql"
doris_sql <"$ROOT/doris/schema.sql" || fail "schema creation failed"
if ! mv_exists; then
  log "applying doris/materialized-view.sql"
  doris_sql <"$ROOT/doris/materialized-view.sql" || fail "materialized view creation failed"
fi
wait_for 60 mv_ready || fail "materialized view mv_revenue_by_category did not finish building"

log "truncating sales.orders so the load is idempotent"
doris_sql -e "TRUNCATE TABLE sales.orders" || fail "truncate failed"

label="orders_$(date +%Y%m%d%H%M%S)_$$"
log "stream load of data/orders.csv with label $label"
response="$(curl -sS --location-trusted -u root: \
  -H "Expect: 100-continue" \
  -H "label: $label" \
  -H "format: csv_with_names" \
  -H "column_separator: ," \
  -H "columns: order_id,customer,product,category,quantity,price,ts" \
  -T "$ROOT/data/orders.csv" \
  "$(service_url be_http)/api/sales/orders/_stream_load")" || fail "stream load request failed"
printf "%s\n" "$response" >"$LOGS/stream-load.json"

summary="$(printf "%s" "$response" | python3 -c 'import json,sys
r = json.load(sys.stdin)
print(r["Status"], r.get("NumberLoadedRows", 0), r.get("NumberFilteredRows", 0), r.get("LoadTimeMs", 0))')"
set -- $summary
[ "$1" = "Success" ] || fail "stream load status $1, see $LOGS/stream-load.json"
[ "$3" = "0" ] || fail "stream load filtered $3 rows, see $LOGS/stream-load.json"
log "stream load loaded $2 rows in $4 ms"
