#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require curl
require python3
port_up "$(service_port ui)" || fail "app is not running, run ./scripts/start-all.sh first"

API="$(service_url ui)"
CSV="$ROOT/data/orders.csv"
WORK="$RUN/expected.csv"
ORIGINAL_1001="$(grep '^1001,' "$CSV")"

expected() {
  awk -F, 'NR>1 && NF>=7 {o[$4]++; q[$4]+=$5; r[$4]+=$5*$6} END {for (c in o) printf "%s %d %d %.2f\n", c, o[c], q[c], r[c]}' "$WORK" | sort
}

side() {
  curl -fsS "$API/api/compare" | python3 -c '
import json, sys
d = json.load(sys.stdin)
for c in d["categories"]:
    s = c[sys.argv[1]]
    if s["orders"] > 0:
        print(c["category"], s["orders"], s["quantity"], s["revenue"])
' "$1" | sort
}

check() {
  local label want got_mysql got_cassandra tries
  label="$1"
  want="$(expected)"
  tries=60
  while [ "$tries" -gt 0 ]; do
    got_mysql="$(side mysql || true)"
    got_cassandra="$(side cassandra || true)"
    if [ "$got_mysql" = "$want" ] && [ "$got_cassandra" = "$want" ]; then break; fi
    sleep 1
    tries=$((tries - 1))
  done
  log "== $label"
  log "awk over expected csv"
  printf "%s\n" "$want"
  log "mysql GROUP BY"
  printf "%s\n" "$got_mysql"
  log "cassandra sales.revenue_by_category"
  printf "%s\n" "$got_cassandra"
  [ "$got_mysql" = "$want" ] || fail "$label: mysql aggregates differ from awk"
  [ "$got_cassandra" = "$want" ] || fail "$label: cassandra aggregates differ from awk"
  log "PASS $label"
}

rows() {
  curl -fsS "$API/api/compare" | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d["mysqlRows"], d["cassandraRows"])'
}

mysql_exec -e "DELETE FROM orders WHERE order_id >= 8000; INSERT IGNORE INTO orders VALUES (1001,'Emma Brown','Building Blocks Set','toys',1,42.87,'2026-01-05T10:05:00Z');" || fail "mysql reset failed"
[ "$(mysql_exec -e "SELECT CONCAT_WS(',', order_id, customer, product, category, quantity, price, ts) FROM orders WHERE order_id = 1001")" = "$ORIGINAL_1001" ] || fail "order 1001 in mysql differs from csv"
cp "$CSV" "$WORK"
check "initial snapshot equals csv"
[ "$(rows)" = "200 200" ] || fail "expected 200 rows in mysql and cassandra, got $(rows)"
log "PASS 200 rows in mysql and cassandra"

mysql_exec -e "INSERT INTO orders VALUES (8101,'Test Buyer','Desk Lamp','home',3,19.99,'2026-02-02T09:00:00Z')" || fail "insert failed"
echo "8101,Test Buyer,Desk Lamp,home,3,19.99,2026-02-02T09:00:00Z" >>"$WORK"
check "INSERT order 8101 into home"

mysql_exec -e "UPDATE orders SET category = 'books', quantity = 5 WHERE order_id = 8101" || fail "update failed"
sed -i.bak 's/^8101,Test Buyer,Desk Lamp,home,3,/8101,Test Buyer,Desk Lamp,books,5,/' "$WORK"
check "UPDATE order 8101 moved home to books with quantity 5"

mysql_exec -e "DELETE FROM orders WHERE order_id = 1001" || fail "delete failed"
sed -i.bak '/^1001,/d' "$WORK"
check "DELETE order 1001 from toys"

mysql_exec -e "INSERT INTO orders VALUES (1001,'Emma Brown','Building Blocks Set','toys',1,42.87,'2026-01-05T10:05:00Z'); DELETE FROM orders WHERE order_id = 8101;" || fail "restore failed"
cp "$CSV" "$WORK"
check "restore back to csv"

counts="$(curl -fsS "$API/api/events" | python3 -c 'import json,sys; c=json.load(sys.stdin)["counts"]; print(c["r"], c["c"], c["u"], c["d"])')"
log "events applied r c u d: $counts"
set -- $counts
[ "$2" -ge 2 ] && [ "$3" -ge 1 ] && [ "$4" -ge 2 ] || fail "expected at least 2 creates, 1 update and 2 deletes"
[ "$(curl -fsS -X POST "$API/api/mysql/update" | python3 -c 'import json,sys; print(json.load(sys.stdin)["result"])')" = "no UI order to update, insert one first" ] || fail "ui update must not touch csv orders"
curl -fsS "$API/" | grep -q "<svg" || fail "ui page not served"
log "PASS all"
