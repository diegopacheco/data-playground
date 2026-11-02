#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require podman
require podman-compose
require curl
require lsof

for image in "$MZ_IMAGE" "$REDPANDA_IMAGE" "$FLINK_BASE_IMAGE" "$PYTHON_IMAGE"; do
  log "pulling $image"
  podman pull -q "$image" >/dev/null || fail "could not pull $image"
done
log "building $FLINK_IMAGE with flink-sql-connector-kafka 5.0.0-2.2"
podman build -q -t "$FLINK_IMAGE" -f "$ROOT/flink/Containerfile" "$ROOT/flink" >/dev/null || fail "flink image build failed"
log "building $APP_IMAGE"
podman build -q -t "$APP_IMAGE" -f "$ROOT/Containerfile" "$ROOT" >/dev/null || fail "app image build failed"
if [ "$(container_state t2-app)" != "absent" ]; then
  podman rm -f t2-app >/dev/null || fail "could not remove the old t2-app container"
fi
mkdir -p "$RUN/logs"
log "setup done"
