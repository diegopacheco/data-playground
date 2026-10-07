#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

port_up "$(service_port thrift)" || fail "thrift is not running on $(service_port thrift), run ./scripts/start-all.sh first"

exec podman exec -it "$THRIFT_CONTAINER" /opt/spark/bin/beeline -u jdbc:hive2://localhost:10000/default -n spark
