#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

port_up "$(service_port redpanda)" || fail "redpanda is not running, run ./scripts/start-all.sh first"
port_up "$(service_port cassandra)" || fail "cassandra is not running, run ./scripts/start-all.sh first"

topic_exists() {
  podman exec "$REDPANDA_CONTAINER" rpk topic list | awk 'NR>1{print $1}' | grep -qx "$TOPIC"
}

if topic_exists; then
  podman exec "$REDPANDA_CONTAINER" rpk topic delete "$TOPIC"
fi
wait_for 30 podman exec "$REDPANDA_CONTAINER" rpk topic create "$TOPIC" -p 1 || fail "could not create topic $TOPIC"

rows="$(tail -n +2 "$ROOT/data/orders.csv" | wc -l | tr -d ' ')"
tail -n +2 "$ROOT/data/orders.csv" | podman exec -i "$REDPANDA_CONTAINER" rpk topic produce "$TOPIC" >"$LOGS/produce.log"
log "produced $rows orders into topic $TOPIC"

require sbt
sbt -batch job/run || fail "spark job failed"
log "spark job wrote sales.revenue_by_category"
