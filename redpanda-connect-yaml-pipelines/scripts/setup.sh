#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require podman
require podman-compose
require curl
require lsof

for image in "$REDPANDA_IMAGE" "$POSTGRES_IMAGE" "$CONNECT_IMAGE" "$PYTHON_IMAGE"; do
  log "pulling $image"
  podman pull -q "$image" >/dev/null || fail "could not pull $image"
done

log "linting the pipelines with redpanda connect"
podman run --rm -v "$ROOT:/connect:ro" -e PG_DSN=postgres://lint -e KAFKA_BROKERS=lint:9092 "$CONNECT_IMAGE" \
  lint /connect/pipelines/orders.yaml /connect/pipelines/customers.yaml /connect/resources/caches.yaml || fail "pipeline lint failed"

log "building $APP_IMAGE"
podman build -q -t "$APP_IMAGE" -f "$ROOT/Containerfile" "$ROOT" >/dev/null || fail "image build failed"
if [ "$(container_state t5-ui)" != "absent" ]; then
  podman rm -f t5-ui >/dev/null || fail "could not remove the old t5-ui container"
fi
mkdir -p "$RUN/logs"
log "setup done"
