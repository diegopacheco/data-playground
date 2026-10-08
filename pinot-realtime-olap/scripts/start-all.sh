#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require podman-compose
require curl
require "$PYTHON"

log "starting infra"
podman-compose up -d >"$LOGS/compose.log" 2>&1 || fail "podman-compose up failed, see $LOGS/compose.log"

wait_for 60 kafka_ready || fail "kafka not ready, see podman logs $KAFKA_CONTAINER"
log "kafka up on $(service_url kafka)"
wait_port_up "$(service_port pinot-controller)" 60 || fail "pinot controller port not open"
wait_for 60 pinot_ready || fail "pinot not healthy, see podman logs $PINOT_CONTAINER"
log "pinot up on $(service_url pinot-controller) and $(service_url pinot-broker)"

podman exec "$KAFKA_CONTAINER" "$KAFKA_BIN/kafka-topics.sh" --bootstrap-server "$KAFKA_INTERNAL" \
  --create --if-not-exists --topic "$TOPIC" --partitions 1 --replication-factor 1 >/dev/null

if table_exists; then
  log "pinot table $TABLE already exists"
else
  add_table >"$LOGS/add-table.log" 2>&1 || fail "pinot AddTable failed, see $LOGS/add-table.log"
  wait_for 30 table_exists || fail "pinot table $TABLE was not created"
  log "pinot schema and REALTIME table $TABLE created"
fi

start_bg ui env UI_PORT="$(service_port ui)" PINOT_BROKER_URL="$(service_url pinot-broker)" \
  PINOT_CONSOLE_URL="$(service_url pinot-controller)" "$PYTHON" "$ROOT/server.py"
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
wait_for 60 orders_ingested "$expected" || fail "pinot ingested $(ingested_orders) of $expected orders"
log "pinot ingested $expected orders"

"$SCRIPTS/status.sh" || true

log "links"
for name in $(service_names); do
  printf "%-17s %s\n" "$name" "$(service_url "$name")"
done
printf "%-17s %s\n" "pinot-console" "$(service_url pinot-controller)/#/query"
printf "%-17s %s\n" "api" "$(service_url ui)/api/categories"
