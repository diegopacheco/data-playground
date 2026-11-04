#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require podman
require podman-compose
require curl
require lsof
require python3

log "pulling $NATS_IMAGE"
podman pull -q "$NATS_IMAGE" >/dev/null || fail "could not pull $NATS_IMAGE"
log "pulling $PYTHON_IMAGE"
podman pull -q "$PYTHON_IMAGE" >/dev/null || fail "could not pull $PYTHON_IMAGE"
log "building $APP_IMAGE with nats-py"
podman build -q -t "$APP_IMAGE" -f "$ROOT/Containerfile" "$ROOT" >/dev/null || fail "image build failed"
if [ "$(container_state r8-app)" != "absent" ]; then
  podman rm -f r8-app >/dev/null || fail "could not remove the old r8-app container"
fi
mkdir -p "$RUN/logs"
log "setup done"
