#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require podman
require podman-compose
require curl
require python3

log "pulling $IMAGE"
podman pull -q "$IMAGE" >/dev/null || fail "could not pull $IMAGE"
log "building the ui image"
compose build >"$LOGS/build.log" 2>&1 || fail "image build failed, see .run/logs/build.log"
log "setup done"
