#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

port="$(service_port cassandra)"
[ -n "$port" ] || fail "cassandra is not declared in scripts/ports.env"
port_up "$port" || fail "cassandra is not running on $port, run ./scripts/start-all.sh first"

if [ "$#" -gt 0 ]; then
  podman exec p1-cassandra cqlsh -k sales "$@"
else
  podman exec -it p1-cassandra cqlsh -k sales
fi
