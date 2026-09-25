#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

port_up "$(service_port cassandra)" || fail "cassandra is not running, run ./scripts/start-all.sh first"
podman exec -it "$CASSANDRA_CONTAINER" cqlsh -k sales "$@"
