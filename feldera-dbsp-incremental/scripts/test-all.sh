#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require podman
for name in $(service_names); do
  port_up "$(service_port "$name")" || fail "$name is down, run scripts/start-all.sh first"
done

mkdir -p "$RUN/logs"
log "running the scaling scenario (up to 1M rows) and then the changes scenario"
api_post run-all >/dev/null || fail "scenarios failed, see: podman logs t3-app"

status=0
podman exec t3-app python -m unittest -v tests.test_incremental >"$RUN/logs/tests.log" 2>&1 || status=$?
cat "$RUN/logs/tests.log"
[ "$status" = "0" ] || fail "tests failed, see .run/logs/tests.log"
log "all tests passed"
