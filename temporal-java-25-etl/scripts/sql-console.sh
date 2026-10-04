#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

port="$(service_port postgres)"
[ -n "$port" ] || fail "postgres is not declared in scripts/ports.env"
pg_ready >/dev/null 2>&1 || fail "postgres is not running on $port, run ./scripts/start-all.sh first"

podman exec -it "$POSTGRES_CONTAINER" psql -U etl -d etl "$@"
