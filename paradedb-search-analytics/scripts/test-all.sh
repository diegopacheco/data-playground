#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require curl
require python3
port_up "$(service_port postgres)" || fail "postgres is down, run scripts/start-all.sh first"
port_up "$(service_port ui)" || fail "ui is down, run scripts/start-all.sh first"

PRODUCTS="$ROOT/data/products.csv"
ORDERS="$ROOT/data/orders.csv"
passed=0

pick() {
  local body
  body="$(api "$1")" || fail "GET $1 failed"
  printf "%s" "$body" | python3 -c "import sys, json; d = json.load(sys.stdin); print($2)"
}

check() {
  if [ "$2" != "$3" ]; then
    fail "$1: expected [$2] got [$3]"
  fi
  passed=$((passed + 1))
  log "ok   $1: $3"
}

log "load"
check "products rows equal products.csv lines" "$(awk 'NR>1' "$PRODUCTS" | wc -l | tr -d ' ')" "$(psql_exec -tAc 'select count(*) from products')"
check "orders rows equal orders.csv lines" "$(awk 'NR>1' "$ORDERS" | wc -l | tr -d ' ')" "$(psql_exec -tAc 'select count(*) from orders')"

log "search relevance"
check "the product whose name and description both hold the terms ranks first" "Wireless Headphones" \
  "$(pick '/api/search?q=wireless+noise+cancelling&mode=any' 'd["results"][0]["name"]')"
check "a partial match ranks below the full match" "True" \
  "$(pick '/api/search?q=wireless+noise+cancelling&mode=any' 'd["results"][0]["score"] > 2 * d["results"][1]["score"]')"
check "all terms mode keeps only documents with every term" "Cast Iron Skillet" \
  "$(pick '/api/search?q=cast+iron&mode=all' '",".join(r["name"] for r in d["results"])')"
check "phrase mode finds the words in order" "Designing Data-Intensive Applications" \
  "$(pick '/api/search?q=data+intensive&mode=phrase' 'd["results"][0]["name"]')"
check "phrase mode rejects the words in the wrong order" "0" \
  "$(pick '/api/search?q=intensive+data&mode=phrase' 'd["total"]')"
check "a typo finds nothing without fuzzy" "0" \
  "$(pick '/api/search?q=hedphones&mode=any' 'd["total"]')"
check "a typo finds the product with fuzzy distance 2" "Wireless Headphones" \
  "$(pick '/api/search?q=hedphones&mode=fuzzy' 'd["results"][0]["name"]')"
check "snippet highlights the matched term" "True" \
  "$(pick '/api/search?q=coffee&mode=any' '"<b>coffee</b>" in d["results"][0]["snippet"]')"
awk_wireless="$(awk -F, 'NR>1 && tolower($0) ~ /wireless/ {n++} END{print n}' "$PRODUCTS")"
check "category facet count equals products.csv lines with the term" "$awk_wireless" \
  "$(pick '/api/search?q=wireless&mode=any&k=35' 'd["total"]')"

log "analytics against awk over orders.csv"
check "total orders, items and revenue" \
  "$(awk -F, 'NR>1{o++; q+=$5; r+=$5*$6} END{printf "%d %d %.2f", o, q, r}' "$ORDERS")" \
  "$(pick '/api/analytics' '"%d %d %.2f" % (d["totals"]["orders"], d["totals"]["items"], d["totals"]["revenue"])')"
check "orders, items and revenue per category" \
  "$(awk -F, 'NR>1{o[$4]++; q[$4]+=$5; r[$4]+=$5*$6} END{for (c in o) printf "%s %d %d %.2f\n", c, o[c], q[c], r[c]}' "$ORDERS" | sort | tr '\n' ';')" \
  "$(pick '/api/analytics' '"".join("%s %d %d %.2f;" % (c["category"], c["orders"], c["items"], c["revenue"]) for c in sorted(d["by_category"], key=lambda c: c["category"]))')"
check "top product by revenue" \
  "$(awk -F, 'NR>1{r[$3]+=$5*$6} END{for (p in r) printf "%.2f|%s\n", r[p], p}' "$ORDERS" | sort -t'|' -k1,1 -rn | head -1 | cut -d'|' -f2)" \
  "$(pick '/api/analytics' 'd["top_products"][0]["product"]')"
check "days with orders" \
  "$(awk -F, 'NR>1{print substr($7, 1, 10)}' "$ORDERS" | sort -u | wc -l | tr -d ' ')" \
  "$(pick '/api/analytics' 'len(d["by_day"])')"
wireless_names="$(awk -F, 'NR>1 && tolower($0) ~ /wireless/ {print $2}' "$PRODUCTS" | paste -sd'|' -)"
check "revenue of orders for products matching the search" \
  "$(awk -F, -v names="$wireless_names" 'BEGIN{n=split(names, a, "|"); for (i=1;i<=n;i++) m[a[i]]=1} NR>1 && ($3 in m){o++; r+=$5*$6} END{printf "%d %.2f", o, r}' "$ORDERS")" \
  "$(pick '/api/analytics?q=wireless&mode=any' '"%d %.2f" % (d["totals"]["orders"], d["totals"]["revenue"])')"
check "category aggregate runs inside the ParadeDB index" "True" \
  "$(pick '/api/analytics' 'any("ParadeDB Aggregate Scan" in line for line in d["plan"])')"

log "all $passed tests passed"
