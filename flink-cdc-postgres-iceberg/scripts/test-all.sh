#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

log "tests started"

require curl
require python3
port_up "$(service_port ui)" || fail "ui is not running, run ./scripts/start-all.sh first"
pid_alive flink || fail "pipeline is not running, run ./scripts/start-all.sh first"

iceberg_categories() {
  compare_json | python3 -c 'import json,sys; [print("%s,%d,%d,%s" % (r["category"], r["orders"], r["quantity"], "%.2f" % r["revenue"])) for r in json.load(sys.stdin)["iceberg"]["categories"]]' | sort
}

iceberg_rows() {
  compare_json | python3 -c 'import json,sys; print(json.load(sys.stdin)["iceberg"]["rows"])'
}

wait_iceberg_equals() {
  local deadline
  deadline=$(( $(date +%s) + 60 ))
  while [ "$(date +%s)" -lt "$deadline" ]; do
    if in_sync && [ "$(iceberg_categories)" = "$1" ]; then return 0; fi
    sleep 1
  done
  return 1
}

log "step 1: reset postgres to data/orders.csv"
psql_run <"$ROOT/sql/reset.sql"

expected_initial="$(awk -F, 'NR>1 && NF>=7 {o[$4]++; q[$4]+=$5; r[$4]+=$5*$6} END {for (c in o) printf "%s,%d,%d,%.2f\n", c, o[c], q[c], r[c]}' "$ROOT/data/orders.csv" | sort)"
wait_iceberg_equals "$expected_initial" || fail "iceberg does not match awk on data/orders.csv, got: $(iceberg_categories)"
[ "$(iceberg_rows)" = "200" ] || fail "iceberg should hold 200 rows, has $(iceberg_rows)"
log "expected from awk on data/orders.csv"
log "$expected_initial"
log "actual from iceberg (flink batch sql)"
iceberg_categories
log "initial load ok: 200 rows, iceberg == postgres == awk"

log "step 2: apply sql/changes.sql (3 inserts, 3 updates, 3 deletes)"
psql_run <"$ROOT/sql/changes.sql"

expected_changed="$(python3 - "$ROOT/data/orders.csv" <<'PY'
import csv, sys
from decimal import Decimal, ROUND_HALF_UP
rows = {int(r["order_id"]): dict(r) for r in csv.DictReader(open(sys.argv[1]))}
rows[2001] = {"category": "garden", "quantity": "2", "price": "35.50"}
rows[2002] = {"category": "books", "quantity": "1", "price": "18.90"}
rows[2003] = {"category": "toys", "quantity": "4", "price": "15.25"}
rows[1001]["quantity"] = "5"
rows[1004]["category"] = "home"
for r in rows.values():
    if r["category"] == "books":
        r["price"] = str((Decimal(r["price"]) * Decimal("1.10")).quantize(Decimal("0.01"), ROUND_HALF_UP))
for k in (1003, 1006, 1007):
    del rows[k]
agg = {}
for r in rows.values():
    a = agg.setdefault(r["category"], [0, 0, Decimal("0")])
    a[0] += 1
    a[1] += int(r["quantity"])
    a[2] += int(r["quantity"]) * Decimal(r["price"])
for c in sorted(agg):
    print("%s,%d,%d,%.2f" % (c, agg[c][0], agg[c][1], agg[c][2]))
PY
)"
expected_changed="$(printf "%s\n" "$expected_changed" | sort)"
wait_iceberg_equals "$expected_changed" || fail "iceberg does not reflect the cdc changes, got: $(iceberg_categories)"
[ "$(iceberg_rows)" = "200" ] || fail "iceberg should hold 200 rows after 3 inserts and 3 deletes, has $(iceberg_rows)"
log "expected from python on data/orders.csv plus the same changes"
log "$expected_changed"
log "actual from iceberg (flink batch sql)"
iceberg_categories

eq_deletes="$(compare_json | python3 -c 'import json,sys; s=json.load(sys.stdin)["snapshots"]; print(max([x["total-equality-deletes"] for x in s] or [0]))')"
[ "$eq_deletes" -gt 0 ] || fail "iceberg has no equality deletes, upsert mode is not active"
log "iceberg equality deletes in current table state: $eq_deletes"

log "postgres side"
psql_run -c "SELECT order_id, category, quantity, price FROM orders WHERE order_id IN (1001,1003,1004,1006,1007,2001,2002,2003) ORDER BY order_id"

log "tests passed"
