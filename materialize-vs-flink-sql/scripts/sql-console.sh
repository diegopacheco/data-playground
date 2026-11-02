#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

[ "$(container_state t2-materialize)" = "running" ] || fail "t2-materialize is not running, run scripts/start-all.sh first"
log "materialize sql console on $(service_url mzsql)"
exec podman exec -it t2-materialize psql -h localhost -p 6875 -U materialize -d materialize "$@"
