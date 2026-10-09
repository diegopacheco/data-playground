#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require podman
require podman-compose
require lsof
require curl
require python3

log "pulling $MINIO_IMAGE"
podman pull -q "$MINIO_IMAGE" >/dev/null || fail "could not pull $MINIO_IMAGE"
log "pulling $PYTHON_IMAGE"
podman pull -q "$PYTHON_IMAGE" >/dev/null || fail "could not pull $PYTHON_IMAGE"

mkdir -p "$RUN/logs"
if podman image exists "$PGLAKE_IMAGE"; then
  log "$PGLAKE_IMAGE already built, skipping"
else
  log "building $PGLAKE_IMAGE from source (postgres 18.6 + pg_lake 3.5.3 + duckdb 1.5.5), this takes a long time, log in .run/logs/build-pglake.log"
  podman build -t "$PGLAKE_IMAGE" -f "$ROOT/pglake/Containerfile" "$ROOT/pglake" >"$RUN/logs/build-pglake.log" 2>&1 || fail "pg_lake image build failed, see .run/logs/build-pglake.log"
fi

log "building $APP_IMAGE"
podman build -q -t "$APP_IMAGE" -f "$ROOT/Containerfile" "$ROOT" >/dev/null || fail "app image build failed"
if podman container exists r11-app; then
  podman rm -f r11-app >/dev/null || fail "could not remove the old r11-app container"
fi

if data_ready; then
  log "dataset already in data/, skipping generation"
else
  log "generating customers and two order batches into data/"
  mkdir -p "$ROOT/data"
  DATA_DIR="$ROOT/data" python3 "$ROOT/app/gen.py" || fail "dataset generation failed"
fi
log "setup done"
