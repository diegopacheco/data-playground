#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require podman-compose
podman image exists "$APP_IMAGE" || fail "image $APP_IMAGE missing, run scripts/setup.sh first"
mkdir -p "$ROOT/results" "$RUN/logs"

log "running the benchmark in r3-bench, log in .run/logs/bench.log"
status=0
compose run --rm r3-bench >"$RUN/logs/bench.log" 2>&1 || status=$?
grep -v 'level=warning' "$RUN/logs/bench.log" | tail -8 || true
[ "$status" = "0" ] || fail "benchmark failed, see .run/logs/bench.log"
