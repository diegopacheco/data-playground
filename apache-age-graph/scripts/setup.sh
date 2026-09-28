#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require podman
require podman-compose
require lsof
require curl

log "pulling $AGE_IMAGE"
podman pull -q "$AGE_IMAGE" >/dev/null || fail "could not pull $AGE_IMAGE"
log "pulling $PYTHON_IMAGE"
podman pull -q "$PYTHON_IMAGE" >/dev/null || fail "could not pull $PYTHON_IMAGE"
log "building $APP_IMAGE with psycopg"
podman build -q -t "$APP_IMAGE" -f "$ROOT/Containerfile" "$ROOT" >/dev/null || fail "image build failed"

if data_ready; then
  log "dataset already in data/, skipping generation"
else
  log "generating customers, products, follows and orders into data/"
  mkdir -p "$ROOT/data"
  podman run --rm -v "$ROOT/data:/data" "$APP_IMAGE" python app/gen.py || fail "dataset generation failed"
fi
log "setup done"
