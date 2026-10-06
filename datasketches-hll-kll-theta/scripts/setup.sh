#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require podman
require podman-compose
require lsof
require curl

log "pulling $PYTHON_IMAGE"
podman pull -q "$PYTHON_IMAGE" >/dev/null || fail "could not pull $PYTHON_IMAGE"
log "building $APP_IMAGE with datasketches and numpy"
podman build -q -t "$APP_IMAGE" -f "$ROOT/Containerfile" "$ROOT" >/dev/null || fail "image build failed"

mkdir -p "$ROOT/results"
if data_ready; then
  log "dataset already in data/, skipping generation"
else
  log "generating 10,000,000 events in $PARTITIONS partitions into data/"
  mkdir -p "$ROOT/data"
  podman run --rm --name r17-gen --memory 1024m -v "$ROOT/data:/data" "$APP_IMAGE" python app/gen.py || fail "dataset generation failed"
fi
log "setup done"
