#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require curl
port_up "$(service_port ui)" || fail "ui is down, run scripts/start-all.sh first"

API="$(service_url ui)/api"
OUT="$RUN/test"
LIFECYCLE="OrderPlaced,OrderPaid,OrderShipped,OrderDelivered"
passed=0
mkdir -p "$OUT"

check() {
  if [ "$2" = "$3" ]; then
    log "PASS $1"
    passed=$((passed + 1))
  else
    printf "FAIL %s\nexpected:\n%s\nactual:\n%s\n" "$1" "$2" "$3" >&2
    exit 1
  fi
}

pg() {
  psql_exec -At -F ' ' -c "$1"
}

dump() {
  kafka_tool kafka-console-consumer --topic "$1" --from-beginning --timeout-ms 5000 \
    --formatter-property print.partition=true --formatter-property print.offset=true \
    --formatter-property print.key=true --formatter-property print.headers=true 2>/dev/null |
    awk -F'\t' '/^Partition:/ {
      id = ""; type = ""; n = split($3, h, ",")
      for (i = 1; i <= n; i++) {
        if (h[i] ~ /^id:/) id = substr(h[i], 4)
        if (h[i] ~ /^eventType:/) type = substr(h[i], 11)
      }
      sub("Partition:", "", $1); sub("Offset:", "", $2)
      print $1, $2, $4, id, type, ($5 == "null" ? "tombstone" : "value")
    }' | sort -k1,1n -k2,2n >"$OUT/$1.txt"
}

lines() {
  sed '/^$/d' | wc -l | tr -d ' '
}

log "reading the four topics with kafka-console-consumer"
pids=""
for topic in outbox.event.order outbox.event.customer dualwrite.db-first.order dualwrite.kafka-first.order; do
  dump "$topic" &
  pids="$pids $!"
done
for pid in $pids; do
  wait "$pid" || fail "kafka-console-consumer failed"
done

ORDER="$OUT/outbox.event.order.txt"
CUSTOMER="$OUT/outbox.event.customer.txt"
cat "$ORDER" "$CUSTOMER" >"$OUT/outbox.txt"

committed="$(pg 'SELECT (SELECT count(*) FROM customers) + (SELECT sum(version) FROM orders)')"
messages="$(lines <"$OUT/outbox.txt")"
unique="$(awk '{print $4}' "$OUT/outbox.txt" | sort -u | lines)"
[ "$committed" -gt 0 ] || fail "no committed transactions found in postgres"

check "committed transactions in postgres equal unique event ids on kafka" "$committed" "$unique"
check "each order has exactly orders.version events under its own key on outbox.event.order" \
  "$(pg 'SELECT order_id, version FROM orders ORDER BY order_id')" \
  "$(awk '!seen[$4]++ {c[$3]++} END {for (k in c) print k, c[k]}' "$ORDER" | sort)"
check "each customer has exactly one event under its own key on outbox.event.customer" \
  "$(pg 'SELECT customer_id, 1 FROM customers ORDER BY customer_id')" \
  "$(awk '!seen[$4]++ {c[$3]++} END {for (k in c) print k, c[k]}' "$CUSTOMER" | sort)"
check "outbox.event.customer carries only CustomerRegistered in the eventType header" "CustomerRegistered" "$(awk '{print $5}' "$CUSTOMER" | sort -u)"
check "outbox.event.order carries only order lifecycle types in the eventType header" "" \
  "$(awk -v ok="$LIFECYCLE" 'BEGIN {n = split(ok, a, ","); for (i = 1; i <= n; i++) t[a[i]] = 1} !($5 in t) {print $5}' "$ORDER" | sort -u)"

attempts="$(pg "SELECT value FROM facts WHERE name = 'rollback_attempts'")"
check "20 transactions were rolled back" "20" "$attempts"
check "rolled-back transactions left no order row and no outbox row" "0 0" \
  "$(pg "SELECT (SELECT count(*) FROM orders WHERE order_id LIKE 'R-%'), (SELECT count(*) FROM outbox WHERE aggregateid LIKE 'R-%')")"
check "rolled-back transactions left no event on kafka" "0" "$(awk '$3 ~ /^R-/' "$OUT/outbox.txt" | lines)"

check "every aggregate id lives in exactly one partition" "0" \
  "$(awk '!seen[$3 " " $1]++ {c[$3]++} END {for (k in c) if (c[k] != 1) print k}' "$OUT/outbox.txt" | lines)"
check "per order the event sequence by offset is the lifecycle up to orders.version" \
  "$(pg "SELECT order_id, array_to_string((string_to_array('$LIFECYCLE', ','))[1:version], ',') FROM orders ORDER BY order_id")" \
  "$(awk '!seen[$4]++ {s[$3] = s[$3] (s[$3] == "" ? "" : ",") $5} END {for (k in s) print k, s[k]}' "$ORDER" | sort)"

deleted="$(pg "SELECT value FROM facts WHERE name = 'delete_outbox_rows'")"
remaining="$(pg 'SELECT count(*) FROM outbox')"
[ "$deleted" -gt 0 ] || fail "no outbox rows were deleted"
check "deleted outbox rows plus remaining outbox rows equal unique events" "$committed" "$((deleted + remaining))"
check "no tombstone on the outbox topics" "0" "$(awk '$6 == "tombstone"' "$OUT/outbox.txt" | lines)"
check "every outbox row still in postgres has its event on kafka" "" \
  "$(comm -23 <(pg 'SELECT id FROM outbox' | sort) <(awk '{print $4}' "$OUT/outbox.txt" | sort -u))"

redelivered=$((messages - unique))
[ "$redelivered" -gt 0 ] || fail "the connect restart redelivered nothing, deduplication was not exercised"
check "the consumer counted every kafka message, redeliveries included" "$messages" "$(pg 'SELECT sum(deliveries) FROM projection')"
check "the consumer processed each event id once" "$unique" "$(pg 'SELECT count(*) FROM processed_events')"
check "events applied to the projection equal committed transactions" "$committed" "$(pg 'SELECT sum(applied) FROM projection')"
check "projection of every order equals orders.version and its last event" "0" \
  "$(pg "SELECT count(*) FROM orders o LEFT JOIN projection p ON p.aggregateid = o.order_id WHERE p.applied IS DISTINCT FROM o.version OR upper(substr(p.last_type, 6)) IS DISTINCT FROM o.status")"

crashes="$(pg "SELECT value FROM facts WHERE name = 'crash_count'")"
dual() {
  local variant rows keys
  variant="$1"
  rows="$(pg "SELECT order_id FROM dual_write_orders WHERE variant = '$variant'" | sort)"
  keys="$(awk '{print $3}' "$OUT/dualwrite.$variant.order.txt" | sort -u)"
  printf "%s %s %s %s\n" "$(printf "%s\n" "$rows" | lines)" "$(printf "%s\n" "$keys" | lines)" \
    "$(comm -23 <(printf "%s\n" "$rows") <(printf "%s\n" "$keys") | lines)" "$(comm -13 <(printf "%s\n" "$rows") <(printf "%s\n" "$keys") | lines)"
}
outbox_rows="$(pg "SELECT order_id FROM orders WHERE order_id LIKE 'K-%'" | sort)"
outbox_keys="$(awk '$3 ~ /^K-/ {print $3}' "$ORDER" | sort -u)"
check "outbox with $crashes crashes: 45 rows, 45 events, nothing missing" "45 45 0 0" \
  "$(printf "%s\n" "$outbox_rows" | lines) $(printf "%s\n" "$outbox_keys" | lines) $(comm -23 <(printf "%s\n" "$outbox_rows") <(printf "%s\n" "$outbox_keys") | lines) $(comm -13 <(printf "%s\n" "$outbox_rows") <(printf "%s\n" "$outbox_keys") | lines)"
check "dual write database first with $crashes crashes: 50 rows, 45 events, 5 rows without event" "50 45 5 0" "$(dual db-first)"
check "dual write kafka first with $crashes crashes: 45 rows, 50 events, 5 events without row" "45 50 0 5" "$(dual kafka-first)"

proof="$(curl -sf "$API/proof")" || fail "GET /api/proof failed"
check "the ui api reports every claim as true" "15 0" \
  "$(printf "%s" "$proof" | "$PY" -c 'import json,sys
claims = json.load(sys.stdin)
print(sum(c["ok"] for c in claims), sum(not c["ok"] for c in claims))')"
check "the ui api committed count equals the psql count" "$committed" \
  "$(printf "%s" "$proof" | "$PY" -c 'import json,sys
print(json.load(sys.stdin)[0]["expected"])')"

log "committed transactions $committed, kafka messages $messages, unique events $unique, redelivered $redelivered"
log "outbox rows deleted $deleted, outbox rows remaining $remaining, rolled back $attempts, crashes per variant $crashes"
log "variant rows events rows_without_event events_without_row"
log "outbox $(printf "%s\n" "$outbox_rows" | lines) $(printf "%s\n" "$outbox_keys" | lines) 0 0"
log "db-first $(dual db-first)"
log "kafka-first $(dual kafka-first)"
log "all $passed tests passed"
