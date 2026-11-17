#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require podman
require podman-compose
require curl
require lsof

for image in "$RISINGWAVE_IMAGE" "$REDPANDA_IMAGE" "$PYTHON_IMAGE" "$PSQL_IMAGE"; do
  log "pulling $image"
  podman pull -q "$image" >/dev/null || fail "could not pull $image"
done
log "building $APP_IMAGE with psycopg and kafka-python"
podman build -q -t "$APP_IMAGE" -f "$ROOT/Containerfile" "$ROOT" >/dev/null || fail "image build failed"
if [ "$(container_state t1-app)" != "absent" ]; then
  podman rm -f t1-app >/dev/null || fail "could not remove the old t1-app container"
fi
mkdir -p "$RUN/logs"
log "setup done"
