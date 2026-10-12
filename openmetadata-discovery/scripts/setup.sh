#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require podman
require podman-compose
require curl
require python3
require lsof

for image in "$OM_IMAGE" "$ES_IMAGE" "$PG_IMAGE" "$PYTHON_IMAGE"; do
  pull_missing "$image"
done

log "building $APP_IMAGE with openmetadata-ingestion"
podman build -q -t "$APP_IMAGE" -f "$ROOT/Containerfile" "$ROOT" >/dev/null || fail "image build failed"
if [ "$(container_state r14-app)" != "absent" ]; then
  podman rm -f r14-app >/dev/null || fail "could not remove the old r14-app container"
fi
mkdir -p "$RUN/logs"
log "setup done"
