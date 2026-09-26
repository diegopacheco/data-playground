#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require curl
require python3
require awk
port_up "$(service_port ui)" || fail "ui is down, run scripts/start-all.sh first"

ORDERS="$ROOT/data/orders.csv"
UI_API="$(service_url ui)/api"
MANAGEMENT="$(service_url lakekeeper)/management/v1"
REST="$(service_url lakekeeper)/catalog/v1"

check() {
  if [ "$2" = "$3" ]; then
    log "PASS $1"
  else
    printf "FAIL %s\nexpected:\n%s\nactual:\n%s\n" "$1" "$2" "$3" >&2
    exit 1
  fi
}

json() {
  python3 -c "import json,sys; d=json.load(sys.stdin); print($1)"
}

expected() {
  awk -F, -v last="$1" 'NR==1 || NR-1>last {next}
    {c[$4]++; q[$4]+=$5; r[$4]+=$5*$6}
    END{for(k in c) printf "%s %d %d %.2f\n", k, c[k], q[k], r[k]}' "$ORDERS" | sort
}

revenue() {
  json '"\n".join("%s %d %d %.2f" % (r["category"], r["total_orders"], r["total_quantity"], r["total_revenue"]) for r in d["rows"])' | sort
}

info="$(curl -sf "$MANAGEMENT/info")" || fail "GET management/v1/info failed"
check "lakekeeper is bootstrapped" "True" "$(printf "%s" "$info" | json 'd["bootstrapped"]')"
check "lakekeeper version" "0.13.6" "$(printf "%s" "$info" | json 'd["version"]')"

warehouses="$(curl -sf "$MANAGEMENT/warehouse")" || fail "GET management/v1/warehouse failed"
check "management api has warehouse lakehouse on s3 bucket lakehouse with sts" "lakehouse lakehouse True" \
  "$(printf "%s" "$warehouses" | json '" ".join("%s %s %s" % (w["name"], w["storage-profile"]["bucket"], w["storage-profile"]["sts-enabled"]) for w in d["warehouses"])')"

prefix="$(curl -sf "$REST/config?warehouse=$BUCKET" | json 'd["defaults"]["prefix"]')" || fail "GET catalog/v1/config failed"
check "iceberg rest config maps warehouse lakehouse to its warehouse id prefix" \
  "$(printf "%s" "$warehouses" | json '[w["warehouse-id"] for w in d["warehouses"] if w["name"] == "lakehouse"][0]')" "$prefix"
check "iceberg rest lists namespace shop" "shop" "$(curl -sf "$REST/$prefix/namespaces" | json '" ".join(".".join(n) for n in d["namespaces"])')"
check "iceberg rest lists table shop.orders" "orders" "$(curl -sf "$REST/$prefix/namespaces/shop/tables" | json '" ".join(t["name"] for t in d["identifiers"])')"

catalog="$(curl -sf "$UI_API/catalog")" || fail "GET /api/catalog failed"
check "two append snapshots with 150 then 200 records" "append:150 append:200" \
  "$(printf "%s" "$catalog" | json '" ".join("%s:%d" % (s["operation"], s["total_records"]) for s in d["snapshots"])')"
check "only the last snapshot is current" "False True" "$(printf "%s" "$catalog" | json '" ".join(str(s["current"]) for s in d["snapshots"])')"

metadata="$(printf "%s" "$catalog" | json 'd["metadata_location"]')"
stored="$(podman exec q4-postgres psql -U lakekeeper -d lakekeeper -tAc "select metadata_location from tabular where name = 'orders' and deleted_at is null")"
check "lakekeeper postgres holds the current metadata pointer of shop.orders" "$metadata" "$stored"

location="$(printf "%s" "$catalog" | json 'd["location"].replace("s3://", "")')"
partitions="$(mc ls --recursive "local/$location/data" | awk '{print $NF}' | cut -d/ -f1 | sort -u | tr '\n' ' ')"
categories="$(awk -F, 'NR>1{print "category=" $4}' "$ORDERS" | sort -u | tr '\n' ' ')"
check "data files on minio are partitioned by category" "$categories" "$partitions"

check "ui container has no s3 keys, it reads with credentials vended by lakekeeper" "0" "$(podman exec q4-ui env | grep -c '^S3_' || true)"

first="$(printf "%s" "$catalog" | json 'd["snapshots"][0]["snapshot_id"]')"
current="$(curl -sf "$UI_API/revenue" | revenue)" || fail "GET /api/revenue failed"
oldest="$(curl -sf "$UI_API/revenue?snapshot=$first" | revenue)" || fail "GET /api/revenue?snapshot=$first failed"
check "duckdb revenue per category on the current snapshot == awk over all 200 csv rows" "$(expected 200)" "$current"
check "duckdb time travel to the first snapshot == awk over the first 150 csv rows" "$(expected 150)" "$oldest"

log "current snapshot per category (category orders quantity revenue):"
printf "%s\n" "$current"
log "first snapshot per category (category orders quantity revenue):"
printf "%s\n" "$oldest"
log "all tests passed"
