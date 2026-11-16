#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require podman
[ "$(container_state t5-postgres)" = "running" ] || fail "postgres is down, run scripts/start-all.sh first"
if [ -t 0 ]; then
  exec podman exec -it t5-postgres psql -U connect -d orders "$@"
fi
exec podman exec -i t5-postgres psql -U connect -d orders "$@"
