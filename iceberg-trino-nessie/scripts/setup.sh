#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require podman
require podman-compose
require curl
require python3

for image in docker.io/pgsty/minio:RELEASE.2026-08-04T00-00-00Z ghcr.io/projectnessie/nessie:0.108.8 docker.io/trinodb/trino:483; do
  log "pulling $image"
  podman pull -q "$image" >/dev/null || fail "could not pull $image"
done
log "building pipeline and ui image"
podman build -q -t i4-iceberg-trino-nessie:latest -f "$ROOT/Containerfile" "$ROOT" >/dev/null || fail "image build failed"
log "setup done"
