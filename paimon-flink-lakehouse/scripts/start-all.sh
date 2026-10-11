#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require podman-compose
require java

podman-compose up -d >/dev/null || fail "podman-compose up failed"
wait_port_up "$(service_port kafka)" 60 || fail "kafka did not open port $(service_port kafka)"
wait_kafka_ready 60 || fail "kafka did not answer within 60 seconds, see podman logs $KAFKA_CONTAINER"
create_topic
log "kafka up on $(service_url kafka), topic $TOPIC ready"

[ -d "$ROOT/target/lib" ] || build_app
mkdir -p "$WAREHOUSE"

start_pipeline
tries=10
while [ "$tries" -gt 0 ]; do
  pid_alive pipeline || fail "pipeline exited, see $LOGS/pipeline.log"
  sleep 1
  tries=$((tries - 1))
done

start_bg ui jvm UiServer 512m
wait_port_up "$(service_port ui)" 60 || fail "ui did not open port $(service_port ui), see $LOGS/ui.log"

"$SCRIPTS/status.sh"

log "links"
for name in $(service_names); do
  printf "%-10s %s\n" "$name" "$(service_url "$name")"
done
printf "%-10s %s\n" "api" "$(service_url ui)/api/revenue"
