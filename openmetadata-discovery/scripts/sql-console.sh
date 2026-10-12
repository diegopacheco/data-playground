#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

[ "$(container_state r14-postgres)" = "running" ] || fail "r14-postgres is down, run scripts/start-all.sh first"
if [ -t 0 ]; then
  exec podman exec -it r14-postgres psql -U postgres -d shop "$@"
fi
exec podman exec -i r14-postgres psql -U postgres -d shop "$@"
