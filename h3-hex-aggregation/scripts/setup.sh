#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require podman
require podman-compose
require curl
require lsof

log "pulling $PYTHON_IMAGE"
podman pull -q "$PYTHON_IMAGE" >/dev/null || fail "could not pull $PYTHON_IMAGE"
log "building $APP_IMAGE with duckdb, the duckdb h3 community extension and h3-py"
podman build -q -t "$APP_IMAGE" -f "$ROOT/Containerfile" "$ROOT" >/dev/null || fail "image build failed"
if [ "$(container_state "$APP_CONTAINER")" != "absent" ]; then
  podman rm -f "$APP_CONTAINER" >/dev/null || fail "could not remove the old $APP_CONTAINER container"
fi
mkdir -p "$RUN/logs"
log "setup done"
