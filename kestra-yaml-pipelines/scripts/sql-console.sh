#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

port_up "$(service_port postgres)" || fail "postgres is not running, run ./scripts/start-all.sh first"

if [ -t 0 ]; then
  podman exec -it "$POSTGRES_CONTAINER" psql -U sales -d sales "$@"
else
  podman exec -i "$POSTGRES_CONTAINER" psql -U sales -d sales "$@"
fi
