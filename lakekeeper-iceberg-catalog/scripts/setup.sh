#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require podman
require podman-compose
require curl
require python3
require awk
require lsof

log "pulling lakekeeper, postgres and minio images"
podman pull -q "$LAKEKEEPER_IMAGE" >/dev/null
podman pull -q "$POSTGRES_IMAGE" >/dev/null
podman pull -q "$MINIO_IMAGE" >/dev/null
log "building pipeline and ui image"
podman build -q -t "$APP_IMAGE" -f "$ROOT/Containerfile" "$ROOT" >/dev/null
log "setup done"
