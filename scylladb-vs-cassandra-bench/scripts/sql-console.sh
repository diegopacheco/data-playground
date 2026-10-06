#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

target="${1:-scylla}"
case "$target" in
  scylla) container="$SCYLLA_CONTAINER" ;;
  cassandra) container="$CASSANDRA_CONTAINER" ;;
  *) fail "usage: $0 [scylla|cassandra]" ;;
esac
port_up "$(service_port "$target")" || fail "$target is not running, run ./scripts/start-all.sh first"
podman exec -it "$container" cqlsh -k bench
