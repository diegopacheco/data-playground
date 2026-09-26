#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

port_up "$(service_port postgres)" || fail "postgres is down, run ./scripts/start-all.sh first"

if [ -t 0 ]; then
  exec podman exec -it "$POSTGRES_CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" "$@"
else
  exec podman exec -i "$POSTGRES_CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" "$@"
fi
