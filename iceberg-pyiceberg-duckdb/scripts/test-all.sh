#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require curl
require python3
require awk
port_up "$(service_port ui)" || fail "ui is down, run scripts/start-all.sh first"

ORDERS="$ROOT/data/orders.csv"
API="$(service_url ui)/api"

expected() {
  awk -F, -v last="$1" -v minq="$2" -v books="$3" '
    NR==1 || NR-1>last || $5<minq {next}
    $4=="books" && books=="drop" {next}
    $4=="books" && books=="double" {$5=$5*2}
    {c[$4]++; q[$4]+=$5; r[$4]+=$5*$6}
    END{for(k in c) printf "%s %d %d %.2f\n", k, c[k], q[k], r[k]}' "$ORDERS" | sort
}

engine() {
  python3 -c 'import json,sys
for r in json.load(sys.stdin)[sys.argv[1]]: print("%s %d %d %.2f" % (r["category"], r["total_orders"], r["total_quantity"], r["total_revenue"]))' "$1" | sort
}

check() {
  if [ "$2" = "$3" ]; then
    log "PASS $1"
  else
    printf "FAIL %s\nexpected:\n%s\nactual:\n%s\n" "$1" "$2" "$3" >&2
    exit 1
  fi
}

snapshots="$(curl -sf "$API/snapshots")" || fail "GET /api/snapshots failed"

field() {
  printf "%s" "$snapshots" | python3 -c 'import json,sys
print(" ".join(str(s[sys.argv[1]]) for s in json.load(sys.stdin)))' "$1"
}

check "snapshot operations are append, append, overwrite, delete, append" "append append overwrite delete append" "$(field operation)"
check "snapshot steps written by pyiceberg" "append-150 append-50 delete-qty-1 overwrite-books overwrite-books" "$(field step)"
check "duckdb iceberg_snapshots sees all 5 snapshots in order" "1 2 3 4 5" "$(field duckdb_sequence_number)"
check "only the last snapshot is current" "False False False False True" "$(field current)"

partitions="$(mc ls --recursive local/warehouse/shop/orders/data | awk '{print $NF}' | cut -d/ -f1 | sort -u | tr '\n' ' ')"
categories="$(awk -F, 'NR>1{print "category=" $4}' "$ORDERS" | sort -u | tr '\n' ' ')"
check "data files on minio are partitioned by category" "$categories" "$partitions"

ids="$(field snapshot_id)"
steps="150:1:keep 200:1:keep 200:2:keep 200:2:drop 200:2:double"
names="append-150 append-50 delete-qty-1 overwrite-books-delete overwrite-books-append"

i=1
for spec in $steps; do
  id="$(printf "%s\n" "$ids" | tr ' ' '\n' | sed -n "${i}p")"
  name="$(printf "%s\n" "$names" | tr ' ' '\n' | sed -n "${i}p")"
  want="$(expected "$(echo "$spec" | cut -d: -f1)" "$(echo "$spec" | cut -d: -f2)" "$(echo "$spec" | cut -d: -f3)")"
  result="$(curl -sf "$API/aggregates?snapshot=$id")" || fail "GET /api/aggregates?snapshot=$id failed"
  check "snapshot $i $name duckdb == awk" "$want" "$(printf "%s" "$result" | engine duckdb)"
  check "snapshot $i $name pyiceberg == awk" "$want" "$(printf "%s" "$result" | engine pyiceberg)"
  i=$((i + 1))
done

current="$(curl -sf "$API/aggregates")" || fail "GET /api/aggregates failed"
check "current table duckdb == awk" "$(expected 200 2 double)" "$(printf "%s" "$current" | engine duckdb)"
check "current table pyiceberg == awk" "$(expected 200 2 double)" "$(printf "%s" "$current" | engine pyiceberg)"

log "current per category (category orders quantity revenue):"
expected 200 2 double
log "oldest snapshot per category (category orders quantity revenue):"
expected 150 1 keep
log "all tests passed"
