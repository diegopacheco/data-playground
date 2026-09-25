#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require podman
require podman-compose
require curl
require python3

log "pulling cassandra image"
podman pull -q docker.io/library/cassandra:5.0.9 >/dev/null
log "building pipeline and ui image"
podman build -q -t p5-dbt-python-cassandra:latest -f "$ROOT/Containerfile" "$ROOT" >/dev/null
log "setup done"
