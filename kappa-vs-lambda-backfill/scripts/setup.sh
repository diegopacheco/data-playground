#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require podman
require podman-compose
require lsof
require curl

for image in "$REDPANDA_IMAGE" "$POSTGRES_IMAGE" "$PYTHON_IMAGE"; do
  log "pulling $image"
  podman pull -q "$image" >/dev/null || fail "could not pull $image"
done
log "building $APP_IMAGE"
podman build -q -t "$APP_IMAGE" -f "$ROOT/Containerfile" "$ROOT" >/dev/null || fail "image build failed"
mkdir -p "$RUN/logs"
log "setup done"
