#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require podman
require podman-compose
require curl
require python3
require lsof

log "pulling druid image"
podman pull -q --platform linux/amd64 docker.io/apache/druid:37.0.0 >/dev/null || fail "could not pull apache/druid:37.0.0"
log "building ui image"
podman build -q -t i32-druid-rollup-ui:latest -f "$ROOT/Containerfile" "$ROOT" >/dev/null || fail "ui image build failed"
chmod +x "$ROOT/druid/launch.sh"
log "setup done"
