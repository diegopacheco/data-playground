#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require podman
for name in $(service_names); do
  port_up "$(service_port "$name")" || fail "$name is down, run scripts/start-all.sh first"
done

mkdir -p "$RUN/logs"
status=0
podman exec r16-app python -m unittest -v tests.test_feast >"$RUN/logs/tests.log" 2>&1 || status=$?
grep -v -e "DeprecationWarning" -e "warnings.warn" "$RUN/logs/tests.log" || true
[ "$status" = "0" ] || fail "tests failed, see .run/logs/tests.log"
log "all tests passed"
