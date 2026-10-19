#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require podman
require podman-compose
require lsof
require curl

log "pulling $REDIS_IMAGE"
podman pull -q "$REDIS_IMAGE" >/dev/null || fail "could not pull $REDIS_IMAGE"
log "pulling $PYTHON_IMAGE"
podman pull -q "$PYTHON_IMAGE" >/dev/null || fail "could not pull $PYTHON_IMAGE"
log "building $APP_IMAGE with feast[redis,duckdb]"
podman build -q -t "$APP_IMAGE" -f "$ROOT/Containerfile" "$ROOT" >/dev/null || fail "image build failed"
mkdir -p "$ROOT/data" "$RUN/logs"
log "setup done, data is generated relative to now on every start"
