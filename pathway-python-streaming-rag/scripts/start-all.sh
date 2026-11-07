#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require podman
require podman-compose
require curl
podman image exists "$APP_IMAGE" || fail "image $APP_IMAGE missing, run scripts/setup.sh first"

log "starting redpanda"
compose up -d t4-redpanda >/dev/null 2>&1 || fail "podman-compose up t4-redpanda failed"
wait_until 60 redpanda_ready || fail "redpanda not healthy, see: podman logs t4-redpanda"
if ! topic_exists; then
  podman exec t4-redpanda rpk topic create "$TOPIC" -p 1 >/dev/null || fail "could not create topic $TOPIC"
  podman exec -i t4-redpanda rpk topic produce "$TOPIC" <"$ROOT/data/kafka-orders.jsonl" >/dev/null || fail "could not publish data/kafka-orders.jsonl"
  log "published data/kafka-orders.jsonl to $TOPIC"
fi
log "redpanda up with topic $TOPIC"

log "starting pathway"
compose up -d t4-pathway >/dev/null 2>&1 || fail "podman-compose up t4-pathway failed"
wait_until 60 pipeline_ready || fail "pathway pipeline did not answer, see: podman logs t4-pathway"
log "pathway up on $(service_url ui)"

"$SCRIPTS/status.sh"

log "links"
for name in $(service_names); do
  printf "%-10s %s\n" "$name" "$(service_url "$name")"
done
printf "%-10s %s\n" windows "$(service_url ui)/api/windows"
printf "%-10s %s\n" totals "$(service_url ui)/api/totals"
printf "%-10s %s\n" docs "$(service_url ui)/api/docs"
