#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

port="$(service_port cassandra)"
[ -n "$port" ] || fail "cassandra is not declared in scripts/ports.env"
port_up "$port" || fail "cassandra is not running on $port, run ./scripts/start-all.sh first"

if command -v cqlsh >/dev/null 2>&1; then
  cqlsh localhost "$port" -k sales "$@"
elif [ -t 0 ]; then
  podman exec -it "$CASSANDRA_CONTAINER" cqlsh -k sales "$@"
else
  podman exec -i "$CASSANDRA_CONTAINER" cqlsh -k sales "$@"
fi
