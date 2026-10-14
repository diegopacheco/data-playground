#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require curl
require awk
port_up "$(service_port ui)" || fail "ui is down, run scripts/start-all.sh first"

DATA="$ROOT/data"
API="$(service_url ui)/api"
DATES="$(ls "$DATA" | sort)"
LAST="$(printf "%s\n" "$DATES" | tail -1)"
PREVIOUS="$(printf "%s\n" "$DATES" | tail -2 | head -1)"
HUBS_AND_LINKS="hub_customer:customer_hk hub_product:product_hk hub_order:order_hk link_order_customer:order_customer_hk link_order_line:order_line_hk"

check() {
  if [ "$2" = "$3" ]; then
    log "PASS $1"
  else
    printf "FAIL %s\nexpected:\n%s\nactual:\n%s\n" "$1" "$2" "$3" >&2
    exit 1
  fi
}

deliveries() {
  local day
  for day in $DATES; do
    printf "%s/%s/%s.csv\n" "$DATA" "$day" "$2"
    [ "$day" != "$1" ] || return 0
  done
}

csv_rows() {
  awk -F, -v keys="$3" -v attrs="$4" 'BEGIN { nk = split(keys, k, " "); na = split(attrs, a, " ") }
    FNR > 1 {
      key = ""; value = ""
      for (i = 1; i <= nk; i++) key = key "|" $k[i]
      for (i = 1; i <= na; i++) value = value "|" $a[i]
      if (!(key in seen) || seen[key] != value) { total++; seen[key] = value }
    } END { print total + 0 }' $(deliveries "$1" "$2")
}

expected_counts() {
  printf "hub_customer %s\n" "$(csv_rows "$1" customers "1" "")"
  printf "hub_product %s\n" "$(csv_rows "$1" products "1" "")"
  printf "hub_order %s\n" "$(csv_rows "$1" orders "1" "")"
  printf "link_order_customer %s\n" "$(csv_rows "$1" orders "1 2" "")"
  printf "link_order_line %s\n" "$(csv_rows "$1" order_lines "1 3 2" "")"
  printf "sat_customer_contact %s\n" "$(csv_rows "$1" customers "1" "2 3")"
  printf "sat_customer_profile %s\n" "$(csv_rows "$1" customers "1" "4 5")"
  printf "sat_product %s\n" "$(csv_rows "$1" products "1" "2 3 4")"
  printf "sat_order %s\n" "$(csv_rows "$1" orders "1" "3 4")"
  printf "sat_order_line %s\n" "$(csv_rows "$1" order_lines "1 3 2" "4 5")"
}

audit_counts() {
  sql "SELECT table_name || ' ' || total_rows FROM audit.load_audit WHERE load_date = '$1' ORDER BY position"
}

live_counts() {
  local pair
  for pair in $HUBS_AND_LINKS sat_customer_contact: sat_customer_profile: sat_product: sat_order: sat_order_line:; do
    printf "%s %s\n" "${pair%%:*}" "$(sql "SELECT count(*) FROM raw_vault.${pair%%:*}")"
  done
}

expected_as_of() {
  local day
  for day in $DATES; do
    awk -F, -v day="$day" 'FNR > 1 { row[$1] = $2 "|" $3 "|" $4 "|" $5 }
      END { for (id in row) printf "%s|%s|%s\n", day, id, row[id] }' $(deliveries "$day" customers)
  done | sort
}

expected_revenue() {
  awk -F, 'FNR == 1 { next }
    FILENAME ~ /products.csv$/ { category[$1] = $3; next }
    { line = $1 "|" $3 "|" $2; product[line] = $3; revenue[line] = $4 * $5 }
    END { for (l in revenue) total[category[product[l]]] += revenue[l]
          for (c in total) printf "%s|%.2f\n", c, total[c] }' $(deliveries "$LAST" products) $(deliveries "$LAST" order_lines) | sort
}

for day in $DATES; do
  check "load $day row counts of 3 hubs, 2 links, 5 satellites match awk over the csv files" "$(expected_counts "$day")" "$(audit_counts "$day")"
done

for pair in $HUBS_AND_LINKS; do
  check "${pair%%:*} never duplicates a key" "0" "$(sql "SELECT count(*) - count(DISTINCT ${pair##*:}) FROM raw_vault.${pair%%:*}")"
done

for name in customers products orders order_lines; do
  cmp -s "$DATA/$PREVIOUS/$name.csv" "$DATA/$LAST/$name.csv" || fail "$name.csv of $LAST is not a re-delivery of $PREVIOUS"
done
log "PASS delivery $LAST is byte-identical to $PREVIOUS"
batches="$(curl -sf "$API/batches")" || fail "GET /api/batches failed"
added() {
  printf "%s" "$batches" | "$PY" -c 'import json,sys
for r in json.load(sys.stdin):
    if r["load_date"] == sys.argv[1] and r["kind"] in sys.argv[2:]: print(r["table_name"], r["delivered_rows"], r["added_rows"])' "$@"
}
check "re-delivered load $LAST adds zero rows to every hub, link and satellite" "" "$(added "$LAST" hub link sat | awk '$3 != 0')"
check "satellites in load $PREVIOUS skip delivered rows whose hashdiff did not change" "" "$(added "$PREVIOUS" sat | awk '$3 >= $2')"

model="$(curl -sf "$API/model")" || fail "GET /api/model failed"
check "api model connects every link and satellite to its parent by hash key" "link_order_customer customer_hk hub_customer
link_order_customer order_hk hub_order
link_order_line order_hk hub_order
link_order_line product_hk hub_product
sat_customer_contact customer_hk hub_customer
sat_customer_profile customer_hk hub_customer
sat_order order_hk hub_order
sat_order_line order_line_hk link_order_line
sat_product product_hk hub_product" "$(printf "%s" "$model" | "$PY" -c 'import json,sys
for e in json.load(sys.stdin)["edges"]: print(e["from"], e["key"], e["to"])' | sort)"

before="$(live_counts)"
summary="$("$PY" "$ROOT/app/pipeline.py" "$LAST")" || fail "dbt build re-run failed, see .run/logs/dbt-$LAST.log"
log "$summary"
check "dbt tests unique, not_null, relationships and custom all pass with zero errors" "WARN=0 ERROR=0 SKIP=0" "$(printf "%s" "$summary" | grep -o 'WARN=[0-9]* ERROR=[0-9]* SKIP=[0-9]*')"
tests="$(grep -c ' PASS ' "$RUN/logs/dbt-$LAST.log" || true)"
[ "$tests" -gt 50 ] || fail "expected more than 50 passing dbt tests, got $tests"
log "PASS dbt ran $tests data tests"
check "running the same load again changes no row count" "$before" "$(live_counts)"
check "live row counts equal awk over all deliveries" "$(expected_counts "$LAST")" "$before"

check "point-in-time table reproduces every customer as of every load date" "$(expected_as_of)" "$(sql "SELECT as_of_date, customer_id, name, email, city, segment FROM business_vault.customer_as_of" | sort)"
history="$(curl -sf "$API/history?customer_id=C020")" || fail "GET /api/history failed"
check "api history of C020 matches awk as of each load date" "$(expected_as_of | grep '|C020|')" "$(printf "%s" "$history" | "$PY" -c 'import json,sys
for r in json.load(sys.stdin)["as_of"]: print("|".join(r[k] for k in ("as_of_date", "customer_id", "name", "email", "city", "segment")))')"

check "mart revenue per category matches awk over the latest state of every order line" "$(expected_revenue)" "$(sql "SELECT p.category, cast(sum(f.revenue) AS DECIMAL(12,2)) FROM mart.fct_order_lines f JOIN mart.dim_product p USING (product_hk) GROUP BY 1" | sort)"
mart="$(curl -sf "$API/mart")" || fail "GET /api/mart failed"
check "api mart total revenue equals the awk total" "$(expected_revenue | awk -F'|' '{ t += $2 } END { printf "%.2f", t }')" "$(printf "%s" "$mart" | "$PY" -c 'import json,sys
print("%.2f" % json.load(sys.stdin)["totals"]["revenue"])')"
check "mart fact has one row per order line link" "$(csv_rows "$LAST" order_lines "1 3 2" "")" "$(sql "SELECT count(*) FROM mart.fct_order_lines")"

log "rows per load from awk (table total):"
for day in $DATES; do
  log "$day $(expected_counts "$day" | tr '\n' ' ')"
done
log "customer C020 as of each load date from awk:"
expected_as_of | grep '|C020|'
log "revenue per category from awk:"
expected_revenue
log "all tests passed"
