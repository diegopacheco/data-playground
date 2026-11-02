#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require podman
require podman-compose
require curl
podman image exists "$APP_IMAGE" || fail "image $APP_IMAGE missing, run scripts/setup.sh first"
podman image exists "$FLINK_IMAGE" || fail "image $FLINK_IMAGE missing, run scripts/setup.sh first"

log "starting redpanda, materialize and flink"
compose up -d t2-redpanda t2-materialize t2-flink-jm t2-flink-tm t2-flink-gateway >/dev/null 2>&1 || fail "podman-compose up failed"
wait_until 60 redpanda_ready || fail "redpanda not healthy, see: podman logs t2-redpanda"
log "redpanda healthy"
wait_until 60 materialize_ready || fail "materialize not ready, see: podman logs t2-materialize"
mz_system -c "ALTER SYSTEM SET enable_logical_compaction_window = true" -c "ALTER SYSTEM SET allow_real_time_recency = true" -c "ALTER SYSTEM SET min_timestamp_interval = '100ms'" >/dev/null 2>&1 || fail "could not set the materialize system parameters"
log "materialize ready (RETAIN HISTORY, real time recency and a 100ms timestamp interval enabled)"
wait_until 60 flink_ready || fail "flink not ready, see: podman logs t2-flink-jm t2-flink-gateway"
log "flink jobmanager, taskmanager and sql gateway ready"

log "starting ui"
compose up -d t2-app >/dev/null 2>&1 || fail "podman-compose up t2-app failed"
wait_until 60 curl -sf -o /dev/null "$(service_url ui)/" || fail "ui did not answer, see: podman logs t2-app"

if [ "$(api result)" = "{}" ]; then
  log "running the comparison once"
  api_post run >/dev/null || fail "comparison run failed, see: podman logs t2-app"
fi

"$SCRIPTS/status.sh"

log "links"
for name in $(service_names); do
  printf "%-10s %s\n" "$name" "$(service_url "$name")"
done
printf "%-10s %s\n" result "$(service_url ui)/api/result"
