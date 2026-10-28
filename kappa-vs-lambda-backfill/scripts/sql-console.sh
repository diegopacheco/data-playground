#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require podman
port_up "$(service_port postgres)" || fail "postgres is down, run scripts/start-all.sh first"
if [ -t 0 ]; then
  podman exec -it r13-postgres psql -U backfill -d backfill "$@"
else
  podman exec -i r13-postgres psql -U backfill -d backfill "$@"
fi
