#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

port_up "$(service_port trino)" || fail "trino is down, run scripts/start-all.sh first"
podman exec -it i4-trino trino --catalog main --schema shop "$@"
