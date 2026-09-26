#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require curl
require python3
port_up "$(service_port ui)" || fail "ui is down, run ./scripts/start-all.sh first"

CSV="$ROOT/data/orders.csv"
failures=0

api() {
  curl -sf "$(service_url ui)/api/$1" | python3 -c 'import json,sys
fields = sys.argv[1].split(",")
for r in json.load(sys.stdin):
    print("|".join("%.2f" % r[f] if isinstance(r[f], float) else str(r[f]) for f in fields))' "$2"
}

check() {
  local name expected actual
  name="$1"
  expected="$2"
  actual="$3"
  if [ -n "$actual" ] && [ "$expected" = "$actual" ]; then
    log "PASS $name"
    printf "%s\n" "$actual" | sed 's/^/  /'
  else
    log "FAIL $name"
    log "  expected:"
    printf "%s\n" "$expected" | sed 's/^/    /'
    log "  actual:"
    printf "%s\n" "$actual" | sed 's/^/    /'
    failures=$((failures + 1))
  fi
}

log "rerunning the stream load pipeline to prove it is idempotent"
"$SCRIPTS/pipeline.sh"

csv_rows="$(tail -n +2 "$CSV" | wc -l | tr -d ' ')"
doris_rows="$(doris_sql -e "SELECT count(*) FROM sales.orders")"
check "row count after two loads equals csv rows" "$csv_rows" "$doris_rows"

mv_used="$(doris_sql -e "EXPLAIN SELECT category, count(order_id), sum(quantity), sum(quantity * price) FROM sales.orders GROUP BY category" | grep -o mv_revenue_by_category | head -1 || true)"
check "revenue per category is answered by the synchronous materialized view" "mv_revenue_by_category" "$mv_used"

expected="$(awk -F, 'NR>1{o[$4]++;q[$4]+=$5;r[$4]+=$5*$6}END{for(k in o)printf "%s|%d|%d|%.2f\n",k,o[k],q[k],r[k]}' "$CSV" | sort -t'|' -k4,4nr)"
check "revenue per category matches awk over the csv" "$expected" "$(api revenue category,total_orders,total_quantity,total_revenue)"

expected="$(awk -F, 'NR>1{k=$3"|"$4;q[k]+=$5;r[k]+=$5*$6}END{for(k in q)printf "%s|%d|%.2f\n",k,q[k],r[k]}' "$CSV" | sort -t'|' -k4,4nr -k1,1 | head -5)"
check "top 5 products by revenue match awk" "$expected" "$(api top-products product,category,total_quantity,total_revenue)"

expected="$(awk -F, 'NR>1{d=substr($7,1,10);o[d]++;r[d]+=$5*$6}END{for(d in o)printf "%s|%d|%.2f\n",d,o[d],r[d]}' "$CSV" | sort)"
check "daily revenue matches awk" "$expected" "$(api daily day,total_orders,total_revenue)"

expected="$(awk -F, 'NR>1{o[$2]++;r[$2]+=$5*$6}END{for(k in o)printf "%s|%d|%.2f\n",k,o[k],r[k]}' "$CSV" | sort -t'|' -k3,3nr -k1,1 | head -5)"
check "top 5 customers by revenue match awk" "$expected" "$(api top-customers customer,total_orders,total_revenue)"

[ "$failures" -eq 0 ] || fail "$failures checks failed"
log "all tests passed"
