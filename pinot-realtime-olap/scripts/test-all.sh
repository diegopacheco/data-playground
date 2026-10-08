#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require curl
require "$PYTHON"
port_up "$(service_port ui)" || fail "ui is not running, run ./scripts/start-all.sh first"

failures=0

api_rows() {
  curl -sf "$(service_url ui)$1" | "$PYTHON" -c 'import json, sys
fields = sys.argv[1].split(",")
for row in json.load(sys.stdin)["rows"]:
    print(" ".join("%.2f" % row[f] if f == "revenue" else str(row[f]).replace(" ", "_") for f in fields))' "$2"
}

check() {
  local name expected actual
  name="$1"
  expected="$2"
  actual="$3"
  if [ "$expected" = "$actual" ]; then
    log "PASS $name"
    printf "%s\n" "$actual" | sed 's/^/  /'
  else
    log "FAIL $name"
    printf "expected\n%s\nactual\n%s\n" "$expected" "$actual" >&2
    failures=$((failures + 1))
  fi
}

rows="$(csv_rows)"

check "every csv row reached pinot through kafka" "$rows" "$(ingested_orders)"

check "totals match awk" \
  "$(awk -F, 'NR>1 {o++; q+=$5; r+=$5*$6; c[$2]=1} END {n=0; for (k in c) n++; printf "%d %d %.2f %d\n", o, q, r, n}' "$CSV")" \
  "$(api_rows /api/stats orders,quantity,revenue,customers)"

check "per category aggregates match awk" \
  "$(awk -F, 'NR>1 {o[$4]++; q[$4]+=$5; r[$4]+=$5*$6} END {for (c in o) printf "%s %d %d %.2f\n", c, o[c], q[c], r[c]}' "$CSV" | sort)" \
  "$(api_rows /api/categories category,orders,quantity,revenue | sort)"

check "top 5 customers by revenue match awk" \
  "$(awk -F, 'NR>1 {k=$2; gsub(/ /, "_", k); o[k]++; q[k]+=$5; r[k]+=$5*$6} END {for (c in o) printf "%s %d %d %.2f\n", c, o[c], q[c], r[c]}' "$CSV" | sort -k4,4nr | head -5)" \
  "$(api_rows /api/customers customer,orders,quantity,revenue)"

check "daily revenue buckets match awk" \
  "$(awk -F, 'NR>1 {d=substr($7, 1, 10); o[d]++; r[d]+=$5*$6} END {for (d in o) printf "%s %d %.2f\n", d, o[d], r[d]}' "$CSV" | sort)" \
  "$(curl -sf "$(service_url ui)/api/daily" | "$PYTHON" -c 'import json, sys, datetime
for row in json.load(sys.stdin)["rows"]:
    day = datetime.datetime.fromtimestamp(row["day"] / 1000, datetime.UTC).date()
    print(day, row["orders"], "%.2f" % row["revenue"])')"

plan="$(pinot_sql "EXPLAIN PLAN FOR SELECT category, count(*), sum(quantity), sum(revenue) FROM $TABLE GROUP BY category")"
check "category aggregation is answered by the star-tree index" "yes" "$(printf "%s" "$plan" | grep -q FILTER_STARTREE_INDEX && echo yes || echo no)"

plan="$(pinot_sql "EXPLAIN PLAN FOR SELECT order_id FROM $TABLE WHERE category = 'toys' LIMIT 1000")"
check "category filter uses the inverted index" "yes" "$(printf "%s" "$plan" | grep -q FILTER_INVERTED_INDEX && echo yes || echo no)"

[ "$failures" -eq 0 ] || fail "$failures checks failed"
log "all tests passed"
