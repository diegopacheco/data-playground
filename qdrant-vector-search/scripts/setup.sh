#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require podman
require podman-compose
require curl
require python3
require lsof

log "pulling $QDRANT_IMAGE"
podman pull -q "$QDRANT_IMAGE" >/dev/null || fail "could not pull $QDRANT_IMAGE"
log "building $APP_IMAGE with fastembed models cached inside"
podman build -q -t "$APP_IMAGE" -f "$ROOT/Containerfile" "$ROOT" >/dev/null || fail "image build failed"
log "setup done"
