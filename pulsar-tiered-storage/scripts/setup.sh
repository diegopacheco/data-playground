#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require podman
require podman-compose
require lsof
require curl
require python3

for image in "$PULSAR_IMAGE" "$MINIO_IMAGE" "$MC_IMAGE" "$PYTHON_IMAGE"; do
  if podman image exists "$image"; then
    log "$image already present"
  else
    log "pulling $image"
    podman pull -q "$image" >/dev/null || fail "could not pull $image"
  fi
done

log "building $BROKER_IMAGE with the tiered storage offloader"
podman build -q -t "$BROKER_IMAGE" -f "$ROOT/Containerfile.pulsar" "$ROOT" >/dev/null || fail "broker image build failed"
log "building $APP_IMAGE with pulsar-client"
podman build -q -t "$APP_IMAGE" -f "$ROOT/Containerfile" "$ROOT" >/dev/null || fail "app image build failed"
for name in r7-broker r7-app; do
  if [ "$(container_state "$name")" != "absent" ]; then
    podman rm -f "$name" >/dev/null || fail "could not remove the old $name container"
  fi
done

if [ -f "$ROOT/data/readings.csv" ]; then
  log "data/readings.csv already exists, skipping generation"
else
  log "generating data/readings.csv"
  mkdir -p "$ROOT/data"
  podman run --rm -v "$ROOT/data:/app/data" "$APP_IMAGE" python app/gen.py || fail "dataset generation failed"
fi
log "setup done"
