#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

port_up "$(service_port clickhouse)" || fail "clickhouse is down, run scripts/start-all.sh first"
exec podman exec -it "$CLICKHOUSE_CONTAINER" clickhouse-client --database bench "$@"
