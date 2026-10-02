#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require podman-compose
[ -f "$ROOT/data/customers.csv" ] || fail "run scripts/setup.sh first"

log "starting storage"
compose up -d i35-minio i35-rest i35-postgres i35-cassandra
wait_ready minio
podman exec i35-minio mc alias set local http://localhost:9000 i35admin i35password >/dev/null
podman exec i35-minio mc mb --ignore-existing local/i35-warehouse
wait_ready rest
wait_ready postgres
wait_ready cassandra 3

log "loading customers into postgres"
podman exec i35-postgres psql -q -U i35 -d crm -v ON_ERROR_STOP=1 -f /sql/postgres.sql
log "loading orders into cassandra"
podman exec i35-cassandra cqlsh -f /sql/cassandra.cql

log "starting trino and ui"
compose build i35-ui
compose up -d i35-trino
compose up -d --force-recreate i35-ui
wait_ready trino 2
wait_ready ui

log "loading products into iceberg through trino"
podman exec i35-ui python app/load_products.py

"$SCRIPTS/status.sh"

log "links"
for name in $(service_names); do
  printf "%-14s %s\n" "$name" "$(service_url "$name")"
done
