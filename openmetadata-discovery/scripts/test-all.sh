#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require podman
require curl
for name in ui openmetadata; do
  port_up "$(service_port "$name")" || fail "$name is down, run scripts/start-all.sh first"
done
wait_until 60 api status || fail "app does not answer on $(service_url ui)"

mkdir -p "$RUN/logs"
status=0
podman exec -e UI_URL=http://localhost:8080 r14-app python -m unittest -v tests.test_catalog >"$RUN/logs/tests.log" 2>&1 || status=$?
cat "$RUN/logs/tests.log"
grep -q '^OK' "$RUN/logs/tests.log" || status=1
[ "$status" = "0" ] || fail "catalog tests failed, see .run/logs/tests.log"
log "all tests passed"
