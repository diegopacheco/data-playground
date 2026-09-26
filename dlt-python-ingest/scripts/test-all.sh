#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require curl
require python3
port_up "$(service_port postgres)" || fail "postgres is down, run scripts/start-all.sh first"
port_up "$(service_port ui)" || fail "app is down, run scripts/start-all.sh first"

mkdir -p "$RUN/logs"
status=0
UI_URL="$(service_url ui)" python3 -m unittest -v tests.test_ingest >"$RUN/logs/tests.log" 2>&1 || status=$?
cat "$RUN/logs/tests.log"
[ "$status" = "0" ] || fail "ingest tests failed"

rows="$(csv_rows)"
source_live="$(pg_scalar "SELECT count(*) FROM orders WHERE NOT deleted")"
source_deleted="$(pg_scalar "SELECT count(*) FROM orders WHERE deleted")"
dest="$(dest_scalar "SELECT count(*) FROM ingest.orders")"
log "csv rows (awk): $rows, source live orders (psql): $source_live, soft deleted: $source_deleted, destination orders (duckdb): $dest"
[ "$source_live" = "$dest" ] || fail "destination has $dest orders, source has $source_live live orders"
[ "$source_live" = "$rows" ] || fail "source live orders $source_live should equal csv rows $rows after 2 deletes and 2 inserts"

source_customers="$(pg_scalar "SELECT count(*) FROM customers")"
dest_customers="$(dest_scalar "SELECT count(*) FROM ingest.customers")"
log "source customers (psql): $source_customers, destination customers (duckdb): $dest_customers"
[ "$source_customers" = "$dest_customers" ] || fail "customers differ: source $source_customers, destination $dest_customers"
log "all tests passed"
