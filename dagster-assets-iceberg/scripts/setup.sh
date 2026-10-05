#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require podman
require podman-compose
require curl
require awk
require python3

mkdir -p "$ROOT/lake"
log "building image $IMAGE"
podman build -t "$IMAGE" -f "$ROOT/Containerfile" "$ROOT" >"$LOGS/build.log" 2>&1 || fail "image build failed, see $LOGS/build.log"
log "setup done"
