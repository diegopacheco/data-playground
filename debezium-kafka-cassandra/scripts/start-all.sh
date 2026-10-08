#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require podman-compose
require curl
[ -d "$ROOT/target/lib" ] || fail "app not built, run ./scripts/setup.sh first"

log "starting infra"
podman-compose up -d >"$LOGS/compose.log" 2>&1 || fail "podman-compose up failed, see $LOGS/compose.log"

wait_for 60 mysql_ready || fail "mysql not ready, see podman logs $MYSQL_CONTAINER"
log "mysql up on $(service_url mysql) with $(mysql_exec -e "SELECT COUNT(*) FROM orders") orders, binlog_format $(mysql_exec -e "SELECT @@binlog_format")"
wait_for 60 kafka_ready || fail "kafka not ready, see podman logs $KAFKA_CONTAINER"
log "kafka up on $(service_url kafka)"
wait_for 60 connect_ready || wait_for 60 connect_ready || fail "kafka connect not ready, see podman logs $CONNECT_CONTAINER"
log "kafka connect up on $(service_url connect)"

curl -fsS -X PUT -H "Content-Type: application/json" --data @"$ROOT/connect/mysql-orders.json" \
  "$(service_url connect)/connectors/$CONNECTOR/config" >"$LOGS/connector.json" || fail "connector registration failed"
wait_for 60 connector_running || fail "connector $CONNECTOR not running, see $(service_url connect)/connectors/$CONNECTOR/status"
wait_for 60 topic_ready || fail "topic $TOPIC was not created by debezium"
log "debezium connector $CONNECTOR running, topic $TOPIC ready"

wait_for 60 cassandra_ready || wait_for 60 cassandra_ready || fail "cassandra not ready, see podman logs $CASSANDRA_CONTAINER"
log "cassandra up on $(service_url cassandra)"

start_bg app "$JAVA_HOME/bin/java" -Xmx256m --enable-native-access=ALL-UNNAMED -cp "$CLASSPATH_APP" sales.App
wait_port_up "$(service_port ui)" 60 || fail "app did not open port $(service_port ui), see $LOGS/app.log"
log "app up on $(service_url ui)"

"$SCRIPTS/status.sh" || true

log "links"
for name in $(service_names); do
  printf "%-10s %s\n" "$name" "$(service_url "$name")"
done
printf "%-10s %s\n" "api" "$(service_url ui)/api/compare"
printf "%-10s %s\n" "events" "$(service_url ui)/api/events"
