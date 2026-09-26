#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require podman
require podman-compose
require curl
require python3

log "pulling redpanda and arroyo images"
podman pull -q docker.io/redpandadata/redpanda:v26.2.3 >/dev/null
podman pull -q ghcr.io/arroyosystems/arroyo:0.15.0 >/dev/null
log "building ui image"
podman build -q -t q1-arroyo-streaming-sql-ui:latest -f "$ROOT/Containerfile" "$ROOT" >/dev/null
log "setup done"
