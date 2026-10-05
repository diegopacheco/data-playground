#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

tigerbeetle_ready || fail "tigerbeetle is not running, run ./scripts/start-all.sh first"
podman exec -it "$TB_CONTAINER" /tigerbeetle repl --cluster=0 --addresses=127.0.0.1:3000 "$@"
