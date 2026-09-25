#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require podman-compose
[ -d "$ROOT/target/lib" ] || fail "app not built, run ./scripts/setup.sh first"

log "starting infra"
podman-compose up -d >"$LOGS/compose.log" 2>&1 || fail "podman-compose up failed, see $LOGS/compose.log"

wait_for 60 kafka_ready || fail "kafka not ready, see podman logs $KAFKA_CONTAINER"
log "kafka up on $(service_url kafka)"
wait_for 60 cassandra_ready || fail "cassandra not ready, see podman logs $CASSANDRA_CONTAINER"
log "cassandra up on $(service_url cassandra)"

podman exec "$KAFKA_CONTAINER" "$KAFKA_BIN/kafka-topics.sh" --bootstrap-server "$KAFKA_INTERNAL" \
  --create --if-not-exists --topic "$TOPIC" --partitions 1 --replication-factor 1 >/dev/null

start_bg streams "$JAVA_HOME/bin/java" -Xmx256m -cp "$CLASSPATH_APP" sales.RevenueStreams
start_bg ui "$JAVA_HOME/bin/java" -Xmx256m -cp "$CLASSPATH_APP" sales.UiServer
wait_port_up "$(service_port ui)" 60 || fail "ui did not open port $(service_port ui), see $LOGS/ui.log"
log "ui up on $(service_url ui)"

produced="$(podman exec "$KAFKA_CONTAINER" "$KAFKA_BIN/kafka-get-offsets.sh" --bootstrap-server "$KAFKA_INTERNAL" --topic "$TOPIC" | awk -F: '{s+=$3} END {print s+0}')"
if [ "$produced" -eq 0 ]; then
  run_java sales.OrdersProducer || fail "producer failed"
else
  log "topic $TOPIC already holds $produced orders, skipping producer"
fi

"$SCRIPTS/status.sh" || true

log "links"
for name in $(service_names); do
  printf "%-10s %s\n" "$name" "$(service_url "$name")"
done
printf "%-10s %s\n" "api" "$(service_url ui)/api/revenue"
