#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

port="$(service_port postgres)"
[ -n "$port" ] || fail "postgres is not declared in scripts/ports.env"
port_up "$port" || fail "postgres is not running on $port, run ./scripts/start-all.sh first"

podman exec -it "$PG_CONTAINER" psql -U "$PG_USER" -d "$PG_DB" "$@"
