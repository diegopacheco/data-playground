#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

port_up "$(service_port rest)" || fail "iceberg rest catalog is down, run scripts/start-all.sh first"
exec "$PY" "$ROOT/app/console.py" "$@"
