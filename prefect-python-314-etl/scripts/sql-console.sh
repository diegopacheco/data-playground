#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

port_up "$POSTGRES_PORT" || fail "postgres is not running on $POSTGRES_PORT, run ./scripts/start-all.sh first"

if command -v psql >/dev/null 2>&1; then
  psql "$PG_DSN" "$@"
elif [ -t 0 ]; then
  podman exec -it i37-postgres psql -U etl -d sales "$@"
else
  podman exec -i i37-postgres psql -U etl -d sales "$@"
fi
