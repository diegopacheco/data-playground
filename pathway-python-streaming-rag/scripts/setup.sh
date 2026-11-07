#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require podman
require podman-compose
require curl
require lsof
require python3

log "pulling $REDPANDA_IMAGE"
podman pull -q "$REDPANDA_IMAGE" >/dev/null || fail "could not pull $REDPANDA_IMAGE"
log "pulling $PYTHON_IMAGE"
podman pull -q "$PYTHON_IMAGE" >/dev/null || fail "could not pull $PYTHON_IMAGE"
log "building $APP_IMAGE with pathway"
podman build -q -t "$APP_IMAGE" -f "$ROOT/Containerfile" "$ROOT" >/dev/null || fail "image build failed"
if [ "$(container_state t4-pathway)" != "absent" ]; then
  podman rm -f t4-pathway >/dev/null || fail "could not remove the old t4-pathway container"
fi
mkdir -p "$RUN/logs"
log "setup done"
