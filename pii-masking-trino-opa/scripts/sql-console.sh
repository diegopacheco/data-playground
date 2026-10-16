#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

trino_ready >/dev/null || fail "trino is down, run scripts/start-all.sh first"
exec podman exec -it s5-trino trino --user "${1:-alice}" --catalog postgres --schema public
