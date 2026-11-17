#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require podman
require curl
for name in ui risingwave admin; do
  port_up "$(service_port "$name")" || fail "$name is down, run scripts/start-all.sh first"
done

mkdir -p "$RUN/logs"
log "rerunning the seeded scenario from empty topics"
api_post run-all >/dev/null || fail "scenario failed, see: podman logs t1-app"

status=0
podman exec t1-app python -m unittest -v tests.test_mvs >"$RUN/logs/tests.log" 2>&1 || status=$?
cat "$RUN/logs/tests.log"
[ "$status" = "0" ] || fail "materialized view tests failed, see .run/logs/tests.log"
log "all tests passed"
