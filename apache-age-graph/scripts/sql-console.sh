#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require podman
port_up "$(service_port postgres)" || fail "postgres is down, run scripts/start-all.sh first"
log "connected to $(service_url postgres), age is preloaded and search_path starts with ag_catalog"
exec podman exec -it -e PGOPTIONS="-c session_preload_libraries=age -c search_path=ag_catalog,public" r15-age psql -U graph -d graph
