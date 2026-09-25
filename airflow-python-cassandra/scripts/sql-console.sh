#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

port_up "$(service_port cassandra)" || fail "cassandra is not running, run ./scripts/start-all.sh first"

if [ -t 0 ]; then
  podman exec -it "$CASSANDRA_CONTAINER" cqlsh -k sales "$@"
else
  podman exec -i "$CASSANDRA_CONTAINER" cqlsh -k sales "$@"
fi
