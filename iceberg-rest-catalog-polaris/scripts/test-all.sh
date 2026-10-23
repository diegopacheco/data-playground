#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

log "tests started"

require curl
require python3
port_up "$(service_port ui)" || fail "ui is not running, run ./scripts/start-all.sh first"
trino_ready || fail "trino is not running, run ./scripts/start-all.sh first"
load_credential || fail "no polaris credentials, run ./scripts/start-all.sh first"

run_pipeline | tee "$LOGS/pipeline.log"

api="$(service_url ui)/api"

awk_aggregates() {
  for f in "$@"; do tail -n +2 "$f"; done | awk -F, '{o[$4]++; q[$4]+=$5; r[$4]+=$5*$6} END {for (c in o) printf "%s %d %d %.2f\n", c, o[c], q[c], r[c]}' | sort
}

log_aggregates() {
  awk -v l="$1" '$1==l{printf "%s %d %d %.2f\n", $2, $3, $4, $5}' "$LOGS/pipeline.log" | sort
}

log_value() {
  awk -v l="$1" '$1==l{print $2; exit}' "$LOGS/pipeline.log"
}

api_aggregates() {
  curl -sf "$api/$1" | python3 -c 'import json,sys
for r in json.load(sys.stdin): print(r["category"], r["orders"], r["quantity"], "%.2f" % r["revenue"])' | sort
}

check() {
  if [ "$2" = "$3" ]; then
    log "PASS $1"
  else
    printf "FAIL %s\nexpected:\n%s\nactual:\n%s\n" "$1" "$2" "$3" >&2
    exit 1
  fi
}

csv_rows="$(tail -n +2 "$ORDERS_CSV" | grep -c .)"
insert_rows="$(tail -n +2 "$TRINO_INSERTS_CSV" | grep -c .)"
before="$(awk_aggregates "$ORDERS_CSV")"
after="$(awk_aggregates "$ORDERS_CSV" "$TRINO_INSERTS_CSV")"

log "awk over orders.csv"
log "$before"
log "awk over orders.csv + trino_inserts.csv"
log "$after"

check "spark wrote every csv row through polaris" "$csv_rows" "$(log_value SPARK_WRITTEN)"
check "trino aggregates on the spark-written table match awk" "$before" "$(log_aggregates TRINO_BEFORE)"
check "trino inserted every row of trino_inserts.csv" "$insert_rows" "$(log_value TRINO_INSERTED)"
check "spark read back every row trino wrote" "$insert_rows" "$(log_value SPARK_READBACK)"
check "spark aggregates after the trino insert match awk" "$after" "$(log_aggregates SPARK_AFTER)"
check "live spark api matches awk" "$after" "$(api_aggregates spark/aggregates)"
check "live trino api matches awk" "$after" "$(api_aggregates trino/aggregates)"

expected_rows="$(tail -n +2 "$TRINO_INSERTS_CSV" | awk -F, '{printf "%s,%s,%s,%s,%s,%.2f,%s\n", $1, $2, $3, $4, $5, $6, $7}')"
actual_rows="$(curl -sf "$api/spark/trino-rows" | python3 -c 'import json,sys
for r in json.load(sys.stdin): print("%s,%s,%s,%s,%s,%.2f,%s" % (r["order_id"], r["customer"], r["product"], r["category"], r["quantity"], r["price"], r["ts"]))')"
check "spark sees the exact rows trino inserted" "$expected_rows" "$actual_rows"

snapshots="$(curl -sf "$api/snapshots" | python3 -c 'import json,sys
for s in json.load(sys.stdin): print(s["engine"], s["operation"], s["added_records"])')"
check "one spark append and one trino append in the table history" "$(printf "spark append %s\ntrino append %s" "$csv_rows" "$insert_rows")" "$snapshots"

catalog="$(curl -sf "$api/polaris" | python3 -c 'import json,sys
d=json.load(sys.stdin)
print(",".join(c["name"] for c in d["catalogs"]["catalogs"]))
print(",".join(".".join(n) for n in d["namespaces"]["namespaces"]))
print(",".join(".".join(t["namespace"] + [t["name"]]) for t in d["tables"]["identifiers"]))
print(",".join(g["privilege"] for g in d["grants"]["grants"]))')"
check "polaris lists catalog, namespace, table and grant" "$(printf "i9_catalog\nsales\nsales.orders\nCATALOG_MANAGE_CONTENT")" "$catalog"

log "tests passed"
