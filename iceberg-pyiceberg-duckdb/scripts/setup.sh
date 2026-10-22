#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require podman
require podman-compose
require curl
require python3
require awk

log "pulling minio and iceberg rest catalog images"
podman pull -q docker.io/pgsty/minio:RELEASE.2026-08-04T00-00-00Z >/dev/null
podman pull -q docker.io/apache/iceberg-rest-fixture:1.10.1 >/dev/null
log "building pipeline and ui image"
podman build -q -t i6-iceberg-pyiceberg-duckdb:latest -f "$ROOT/Containerfile" "$ROOT" >/dev/null
log "setup done"
