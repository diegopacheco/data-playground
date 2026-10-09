#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require podman
require podman-compose
require curl
require python3

log "pulling minio image"
podman pull -q docker.io/pgsty/minio:RELEASE.2026-08-04T00-00-00Z >/dev/null
log "building pipeline and ui image"
podman build -q -t i5-delta-rs-python:latest -f "$ROOT/Containerfile" "$ROOT" >/dev/null
log "setup done"
