#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require curl
port_up "$(service_port ui)" || fail "ui is down, run scripts/start-all.sh first"

ORDERS="$ROOT/data/orders.csv"
API="$(service_url ui)/api"
CATALOG="$(service_url rest)/v1/namespaces/redpanda/tables"

expected() {
  awk -F, 'NR>1 { c[$4]++; q[$4] += $5; r[$4] += $5 * $6 }
    END { for (k in c) printf "%s %d %d %.2f\n", k, c[k], q[k], r[k] }' "$ORDERS" | sort
}

field() {
  printf "%s" "$tables" | "$PY" -c 'import json,sys
t=[x for x in json.load(sys.stdin) if x["topic"]==sys.argv[1]][0]
print(eval(sys.argv[2]))' "$1" "$2"
}

api_categories() {
  field "$1" '"\n".join("%s %d %d %.2f" % (c["category"], c["orders"], c["quantity"], c["revenue"]) for c in t["categories"])' | sort
}

check() {
  if [ "$2" = "$3" ]; then
    log "PASS $1"
  else
    printf "FAIL %s\nexpected:\n%s\nactual:\n%s\n" "$1" "$2" "$3" >&2
    exit 1
  fi
}

tables="$(curl -sf "$API/tables")" || fail "GET /api/tables failed"
batches="$(curl -sf "$API/batches")" || fail "GET /api/batches failed"
produced="$(($(wc -l <"$ORDERS") - 1))"

check "no kafka connect: the stack is only redpanda, iceberg rest catalog and minio" "s1-minio s1-redpanda s1-rest" "$(podman ps --format '{{.Names}}' | grep '^s1-' | sort | tr '\n' ' ' | sed 's/ $//')"
check "rest catalog lists the two tables redpanda created" "orders_kv orders_typed" "$(curl -sf "$CATALOG" | "$PY" -c 'import json,sys; print(" ".join(sorted(i["name"] for i in json.load(sys.stdin)["identifiers"])))')"

for topic in orders_kv orders_typed; do
  watermark="$(rpk topic describe "$topic" -p | awk 'NR>1 {s += $NF} END {print s}')"
  check "$topic: topic high watermark equals the $produced orders in the csv" "$produced" "$watermark"
  check "$topic: iceberg row count equals the topic high watermark" "$watermark" "$(field "$topic" 't["rows"]')"
  check "$topic: every kafka offset is in iceberg exactly once" "$produced 0 $((produced - 1))" "$(field "$topic" '"%d %d %d" % (t["distinct_offsets"], t["first_offset"], t["last_offset"])')"
  check "$topic: orders, quantity and revenue per category match awk" "$(expected)" "$(api_categories "$topic")"
  check "$topic: iceberg snapshots add up to $produced records" "$produced" "$(field "$topic" 'sum(s["added_records"] for s in t["snapshots"])')"
  files="$(mc ls -r "local/s1-lake/iceberg/redpanda/$topic/data/" | grep -c '\.parquet$' || true)"
  check "$topic: parquet files on minio equal data files in the snapshots" "$(field "$topic" 'sum(s["added_data_files"] for s in t["snapshots"])')" "$files"
  slow="$(field "$topic" 'sum(1 for s in t["snapshots"] if not 0 < s["commit_lag_s"] <= 60)')"
  check "$topic: every snapshot committed within 60s of its newest record" "0" "$slow"
done

check "orders_kv: topic property redpanda.iceberg.mode" "key_value" "$(rpk topic describe orders_kv -c | awk '$1=="redpanda.iceberg.mode"{print $2}')"
check "orders_typed: topic property redpanda.iceberg.mode" "value_schema_id_prefix" "$(rpk topic describe orders_typed -c | awk '$1=="redpanda.iceberg.mode"{print $2}')"
check "orders_kv: table is only the redpanda struct and an opaque value" "redpanda:STRUCT value:BLOB" "$(field orders_kv '" ".join(c["column_name"] + ":" + c["column_type"].split("(")[0] for c in t["columns"])')"
check "orders_typed: schema registry json schema became typed columns" "category:VARCHAR customer:VARCHAR order_id:BIGINT price:DOUBLE product:VARCHAR quantity:BIGINT ts:TIMESTAMP WITH TIME ZONE" "$(field orders_typed '" ".join(sorted(c["column_name"] + ":" + c["column_type"] for c in t["columns"] if c["column_name"] != "redpanda"))')"
check "schema registry holds the json schema used by orders_typed" "JSON" "$(curl -sf "$(service_url registry)/subjects/orders_typed-value/versions/latest" | "$PY" -c 'import json,sys; print(json.load(sys.stdin)["schemaType"])')"

late="$(printf "%s" "$batches" | "$PY" -c 'import json,sys; print(sum(1 for b in json.load(sys.stdin)["batches"] if not 0 < b["visible_after_s"] <= 60))')"
check "every produced batch became readable from iceberg within 60s" "0" "$late"

reader() {
  "$PY" -c 'import sys
sys.path.insert(0, sys.argv[1])
from lake import connect
for r in connect().execute("SELECT category, count(*), sum(quantity), sum(quantity * price::DECIMAL(10,2)) FROM lake.redpanda.orders_typed GROUP BY category").fetchall(): print("%s %d %d %.2f" % r)' "$ROOT/app" | sort
}
check "a second duckdb process reading the rest catalog sees the same aggregates" "$(expected)" "$(reader)"

log "produce to readable lag per batch (batch topic records seconds):"
printf "%s" "$batches" | "$PY" -c 'import json,sys
for b in json.load(sys.stdin)["batches"]: print(b["batch"], b["topic"], b["records"], b["visible_after_s"])'
log "newest record to iceberg commit lag per snapshot (topic added_records seconds):"
for topic in orders_kv orders_typed; do
  field "$topic" '"\n".join("%s %d %.2f" % (t["topic"], s["added_records"], s["commit_lag_s"]) for s in t["snapshots"])'
done
log "license: $(curl -sf "$API/license" | "$PY" -c 'import json,sys,time; l=json.load(sys.stdin); print(l["org"] + ", type " + l["type"] + ", license_status " + l["license_status"] + ", expires in %d days" % ((l["expires"] - time.time()) / 86400))')"
log "per category from awk (category orders quantity revenue):"
expected
log "all tests passed"
