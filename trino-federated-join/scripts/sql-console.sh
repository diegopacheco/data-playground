#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

trino_ready >/dev/null || fail "trino is not running, run scripts/start-all.sh first"
podman exec -it i35-trino trino "$@"
