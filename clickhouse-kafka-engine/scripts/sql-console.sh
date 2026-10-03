#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

clickhouse_ready >/dev/null 2>&1 || fail "clickhouse is not running, run ./scripts/start-all.sh first"
exec podman exec -it "$CLICKHOUSE_CONTAINER" clickhouse-client --database sales
