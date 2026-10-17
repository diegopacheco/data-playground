#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require curl
port_up "$(service_port ui)" || fail "ui is down, run scripts/start-all.sh first"

ORDERS="$ROOT/data/orders.csv"
API="$(service_url ui)/api"

expected() {
  awk -F, -v last="$1" -v bump="$2" -v drop="$3" 'NR>1 && NR<=last+1 {
      p = $6; if (bump && $4 == "electronics") p += 5
      if (drop && $5 == 5) next
      c[$4]++; q[$4] += $5; r[$4] += $5 * p
    } END { for (k in c) printf "%s %d %d %.2f\n", k, c[k], q[k], r[k] }' "$ORDERS" | sort
}

api_snapshot() {
  printf "%s" "$snapshots" | "$PY" -c 'import json,sys
s=[x for x in json.load(sys.stdin) if x["snapshot_id"]==int(sys.argv[1])][0]
for c in s["categories"]: print("%s %d %d %.2f" % (c["category"], c["orders"], c["quantity"], c["revenue"]))' "$1" | sort
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

check "snapshot 1 created table is empty before load" "" "$(api_snapshot 1)"
check "snapshot 2 client A 150 orders match awk" "$(expected 150 0 0)" "$(api_snapshot 2)"
check "snapshot 3 client B remaining 50 orders match awk" "$(expected 200 0 0)" "$(api_snapshot 3)"
check "snapshot 4 update electronics price +5 matches awk" "$(expected 200 1 0)" "$(api_snapshot 4)"
check "snapshot 5 delete quantity 5 matches awk" "$(expected 200 1 1)" "$(api_snapshot 5)"
check "snapshot 6 add column keeps data" "$(expected 200 1 1)" "$(api_snapshot 6)"
check "snapshot 7 channel update keeps revenue" "$(expected 200 1 1)" "$(api_snapshot 7)"

pg() {
  psql_exec -At -F ' ' -c "$1"
}

check "postgres ducklake_snapshot has 8 snapshots" "8" "$(pg 'SELECT count(*) FROM ducklake_snapshot')"
check "postgres commit messages written by both clients" "client A loads first 150 orders
client B loads remaining 50 orders" "$(pg "SELECT commit_message FROM ducklake_snapshot_changes WHERE commit_message LIKE 'client%' ORDER BY snapshot_id")"
check "postgres ducklake_column shows channel added at snapshot 6" "channel 6" "$(pg "SELECT column_name, begin_snapshot FROM ducklake_column WHERE column_name = 'channel'")"
check "postgres ducklake_column keeps price column active after schema change" "price" "$(pg "SELECT column_name FROM ducklake_column WHERE column_name = 'price' AND end_snapshot IS NULL")"

files="$(pg 'SELECT path FROM ducklake_data_file UNION ALL SELECT path FROM ducklake_delete_file' | sort)"
objects="$(mc ls -r local/i10-lake/main/orders/ | awk '{print $NF}' | sort)"
missing="$(comm -23 <(printf "%s\n" "$files") <(printf "%s\n" "$objects"))"
check "every parquet file in the postgres catalog exists on minio" "" "$missing"
log "catalog lists $(printf "%s\n" "$files" | wc -l | tr -d ' ') live parquet files, minio holds $(printf "%s\n" "$objects" | wc -l | tr -d ' ') objects"

reader() {
  "$PY" -c 'import sys
sys.path.insert(0, sys.argv[1])
from lake import connect
c = connect()
print(c.execute("SELECT count(*) FROM lake.orders").fetchone()[0], c.execute("SELECT count(*) FROM lake.orders AT (VERSION => 2)").fetchone()[0])' "$ROOT/app"
}
reader >"$RUN/reader1.out" &
p1=$!
reader >"$RUN/reader2.out" &
p2=$!
wait "$p1" || fail "reader process 1 failed"
wait "$p2" || fail "reader process 2 failed"
live="$(awk -F, 'NR>1 && $5 != 5' "$ORDERS" | wc -l | tr -d ' ') 150"
check "duckdb process 1 attached the same ducklake" "$live" "$(cat "$RUN/reader1.out")"
check "duckdb process 2 attached the same ducklake" "$live" "$(cat "$RUN/reader2.out")"

log "latest per category from awk (category orders quantity revenue):"
expected 200 1 1
log "all tests passed"
