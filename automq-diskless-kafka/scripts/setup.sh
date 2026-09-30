#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require podman
require podman-compose
require lsof
require curl
require python3

for image in "$AUTOMQ_IMAGE" "$MINIO_IMAGE" "$PYTHON_IMAGE"; do
  if podman image exists "$image"; then
    log "$image already present"
  else
    log "pulling $image"
    podman pull -q "$image" >/dev/null || fail "could not pull $image"
  fi
done
log "building $APP_IMAGE with confluent-kafka"
podman build -q -t "$APP_IMAGE" -f "$ROOT/Containerfile" "$ROOT" >/dev/null || fail "image build failed"

if data_ready; then
  log "data/orders.jsonl already present, skipping generation"
else
  log "generating data/orders.jsonl"
  mkdir -p "$ROOT/data"
  podman run --rm -v "$ROOT/data:/data" "$APP_IMAGE" python app/gen.py || fail "data generation failed"
fi
mkdir -p "$ROOT/results" "$RUN/logs"
log "setup done"
