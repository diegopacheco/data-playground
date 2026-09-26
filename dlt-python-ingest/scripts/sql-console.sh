#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

port_up "$(service_port postgres)" || fail "postgres is down, run scripts/start-all.sh first"

if [ -t 0 ]; then
  podman exec -it "$PG_CONTAINER" psql -U shop -d shop "$@"
else
  psql_exec "$@"
fi
