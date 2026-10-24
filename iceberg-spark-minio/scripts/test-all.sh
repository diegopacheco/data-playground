#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

log "tests started"

require curl
require python3
port_up "$(service_port ui)" || fail "ui is not running, run ./scripts/start-all.sh first"
catalog_ready || fail "iceberg rest catalog is not running, run ./scripts/start-all.sh first"

run_lake_job | tee "$LOGS/lake-job.log"

api="$(service_url ui)/api"
first_batch_filter='$1<=1100'

csv_revenue() {
  tail -n +2 "$ORDERS_CSV" | awk -F, "$1"'{o[$4]++; q[$4]+=$5; r[$4]+=$5*$6} END {for (c in o) printf "%s %d %d %.2f\n", c, o[c], q[c], r[c]}' | sort
}

api_revenue() {
  curl -sf "$api/revenue?snapshot=$1" | python3 -c 'import json,sys
for r in json.load(sys.stdin)["rows"]: print(r["category"], r["orders"], r["quantity"], "%.2f" % float(r["revenue"]))' | sort
}

travel_rows() {
  awk -v h="$1" 'index($0, h)==1{f=1; next} f && /^\|[[:space:]]*[0-9]+\|$/{gsub(/[| ]/, ""); print; exit}' "$LOGS/lake-job.log"
}

check() {
  if [ "$2" = "$3" ]; then
    log "PASS $1"
  else
    printf "FAIL %s\nexpected:\n%s\nactual:\n%s\n" "$1" "$2" "$3" >&2
    exit 1
  fi
}

snapshots="$(curl -sf "$api/snapshots" | python3 -c 'import json,sys
for s in json.load(sys.stdin): print(s["operation"], s["added_records"], s["total_records"])')"
check "two append snapshots of 100 rows each" "$(printf "append 100 100\nappend 100 200")" "$snapshots"

check "VERSION AS OF first snapshot sees 100 rows" "100" "$(travel_rows "== time travel VERSION AS OF")"
check "TIMESTAMP AS OF first commit sees 100 rows" "100" "$(travel_rows "== time travel TIMESTAMP AS OF")"
check "latest snapshot sees 200 rows" "200" "$(travel_rows "== latest")"

schema="$(curl -sf "$api/schema" | python3 -c 'import json,sys; print(",".join(f["name"] for f in json.load(sys.stdin)))')"
check "schema evolved with customer renamed and channel added" "order_id,customer_name,product,category,quantity,price,ts,channel" "$schema"

expected_first="$(csv_revenue "$first_batch_filter")"
actual_first="$(api_revenue first)"
log "first snapshot, csv vs api"
log "$expected_first"
check "revenue at first snapshot matches awk on first 100 csv rows" "$expected_first" "$actual_first"

expected_latest="$(csv_revenue 1)"
actual_latest="$(api_revenue latest)"
log "latest snapshot, csv vs api"
log "$expected_latest"
check "revenue at latest snapshot matches awk on all csv rows" "$expected_latest" "$actual_latest"

log "tests passed"
