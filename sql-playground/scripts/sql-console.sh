#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

port="$(service_port postgres)"
port_up "$port" || fail "postgres is not running on $port, run ./scripts/start-all.sh first"

if command -v psql >/dev/null 2>&1; then
  PGPASSWORD=playground psql -h localhost -p "$port" -U playground -d playground "$@"
else
  podman exec -it sql-playground-postgres psql -U playground -d playground "$@"
fi
