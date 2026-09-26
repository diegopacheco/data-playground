#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require podman
require podman-compose
require curl
require python3

log "pulling postgres image"
podman pull -q "$POSTGRES_IMAGE" >/dev/null
log "building maven stage with beam unit tests"
podman build -q --target build -t "$BUILD_IMAGE" -f "$ROOT/Containerfile" "$ROOT" >/dev/null || fail "maven build failed"
log "building runtime image"
podman build -q -t "$IMAGE" -f "$ROOT/Containerfile" "$ROOT" >/dev/null || fail "runtime image build failed"
log "setup done"
