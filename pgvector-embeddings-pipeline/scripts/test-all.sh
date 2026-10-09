#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

port_up "$(service_port ui)" || fail "ui is down, run scripts/start-all.sh first"
port_up "$(service_port postgres)" || fail "postgres is down, run scripts/start-all.sh first"

csv_products="$(awk -F, 'NR>1{print $3}' "$ROOT/data/orders.csv" | sort -u | wc -l | tr -d ' ')"
db_products="$(psql_exec -tAc "select count(*) from products where embedding is not null")"
log "awk distinct products in orders.csv: $csv_products, embedded rows in postgres: $db_products"
[ "$csv_products" = "$db_products" ] || fail "embedding row count $db_products differs from products count $csv_products"

log "recall@10 and latency from EXPLAIN ANALYZE"
psql_exec -c "select coalesce(m->>'index', m->>'mode') as mode, m->>'ef_search' as ef_search, m->>'recall' as recall, m->>'avg_ms' as avg_ms from pipeline_results, jsonb_array_elements(payload->'bench'->'modes') m"

mkdir -p "$RUN/logs"
status=0
PGPORT="$(service_port postgres)" UI_PORT="$(service_port ui)" "$PY" -m unittest -v tests.test_pipeline >"$RUN/logs/tests.log" 2>&1 || status=$?
grep -v "Fetching\|RuntimeWarning" "$RUN/logs/tests.log" || true
[ "$status" = "0" ] || fail "python tests failed"
log "all tests passed"
