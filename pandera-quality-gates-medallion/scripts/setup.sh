#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require podman
require podman-compose
require lsof
require curl

log "pulling $PYTHON_IMAGE"
podman pull -q "$PYTHON_IMAGE" >/dev/null || fail "could not pull $PYTHON_IMAGE"
log "building $APP_IMAGE with pandera, pandas and duckdb"
podman build -q -t "$APP_IMAGE" -f "$ROOT/Containerfile" "$ROOT" >/dev/null || fail "image build failed"

if data_ready; then
  log "incoming batches already in data/incoming, skipping generation"
else
  log "generating the incoming batches into data/incoming"
  mkdir -p "$ROOT/data"
  podman run --rm -v "$ROOT/data:/data" "$APP_IMAGE" python app/gen.py || fail "batch generation failed"
fi
log "setup done"
