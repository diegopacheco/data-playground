#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require podman
require podman-compose
require curl
require lsof

log "pulling $RUST_IMAGE"
podman pull -q "$RUST_IMAGE" >/dev/null || fail "could not pull $RUST_IMAGE"
log "pulling $PYTHON_IMAGE"
podman pull -q "$PYTHON_IMAGE" >/dev/null || fail "could not pull $PYTHON_IMAGE"
log "building $APP_IMAGE (rust release build + duckdb cli)"
podman build -q -t "$APP_IMAGE" -f "$ROOT/Containerfile" "$ROOT" >/dev/null || fail "image build failed"
podman volume exists "$CARGO_VOLUME" || podman volume create "$CARGO_VOLUME" >/dev/null || fail "could not create volume $CARGO_VOLUME"
log "setup done"
