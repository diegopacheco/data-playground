#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

port="$(service_port cassandra)"
[ -n "$port" ] || fail "cassandra is not declared in scripts/ports.env"
cql_ready || fail "cassandra is not running on $port, run ./scripts/start-all.sh first"

podman exec -it "$CASSANDRA_CONTAINER" cqlsh -k sales "$@"
