#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require podman
require podman-compose
require curl
require python3
require lsof

log "pulling $BASE_IMAGE"
podman pull -q "$BASE_IMAGE" >/dev/null || fail "could not pull $BASE_IMAGE"
log "building $APP_IMAGE with the fastembed model cached and the product images generated inside"
podman build -q -t "$APP_IMAGE" -f "$ROOT/Containerfile" "$ROOT" >/dev/null || fail "image build failed"
log "setup done"
