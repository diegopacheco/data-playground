#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require podman
require podman-compose
require curl
require lsof

log "pulling $FELDERA_IMAGE (about 8 GB, it ships the SQL compiler and the Rust toolchain)"
podman image exists "$FELDERA_IMAGE" || podman pull -q "$FELDERA_IMAGE" >/dev/null || fail "could not pull $FELDERA_IMAGE"
log "pulling $PYTHON_IMAGE"
podman pull -q "$PYTHON_IMAGE" >/dev/null || fail "could not pull $PYTHON_IMAGE"
log "building $APP_IMAGE with duckdb"
podman build -q -t "$APP_IMAGE" -f "$ROOT/Containerfile" "$ROOT" >/dev/null || fail "image build failed"
if [ "$(container_state t3-app)" != "absent" ]; then
  podman rm -f t3-app >/dev/null || fail "could not remove the old t3-app container"
fi
mkdir -p "$RUN/logs"
log "setup done"
