#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require podman-compose
require "$PYTHON"

log "starting infra"
podman-compose up -d >"$LOGS/compose.log" 2>&1 || fail "podman-compose up failed, see $LOGS/compose.log"

wait_for 60 kafka_ready || fail "kafka not ready, see podman logs $KAFKA_CONTAINER"
log "kafka up on $(service_url kafka)"
wait_for 60 clickhouse_ready || fail "clickhouse not ready, see podman logs $CLICKHOUSE_CONTAINER"
log "clickhouse up on $(service_url clickhouse)"

podman exec "$KAFKA_CONTAINER" "$KAFKA_BIN/kafka-topics.sh" --bootstrap-server "$KAFKA_INTERNAL" \
  --create --if-not-exists --topic "$TOPIC" --partitions 1 --replication-factor 1 >/dev/null

ch --multiquery <"$ROOT/sql/schema.sql" || fail "schema creation failed"
log "clickhouse kafka engine, merge tree and materialized views ready"

start_bg ui env UI_PORT="$(service_port ui)" CLICKHOUSE_URL="$(service_url clickhouse)" "$PYTHON" "$ROOT/server.py"
wait_port_up "$(service_port ui)" 30 || fail "ui did not open port $(service_port ui), see $LOGS/ui.log"
log "ui up on $(service_url ui)"

produced="$(topic_size)"
if [ "$produced" -eq 0 ]; then
  log "producing $(csv_rows) orders as JSON into topic $TOPIC"
  produce_orders || fail "kafka console producer failed"
else
  log "topic $TOPIC already holds $produced orders, skipping producer"
fi

expected="$(topic_size)"
wait_for 60 orders_ingested "$expected" || fail "clickhouse ingested $(ingested_orders) of $expected orders"
log "clickhouse ingested $expected orders"

"$SCRIPTS/status.sh" || true

log "links"
for name in $(service_names); do
  printf "%-12s %s\n" "$name" "$(service_url "$name")"
done
printf "%-12s %s\n" "api" "$(service_url ui)/api/totals"
