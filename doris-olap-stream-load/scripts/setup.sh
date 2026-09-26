#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require podman
require podman-compose
require curl
require python3

ensure_max_map_count
log "vm.max_map_count is $(podman_vm sysctl -n vm.max_map_count | tr -d '\r')"

log "pulling doris fe and be images"
podman pull -q docker.io/apache/doris:fe-4.1.4 >/dev/null
podman pull -q docker.io/apache/doris:be-4.1.4 >/dev/null
log "building ui image"
podman build -q -t q3-doris-olap-ui:latest -f "$ROOT/Containerfile" "$ROOT" >/dev/null
log "setup done"
