#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require podman
require python3
for name in $(service_names); do
  port_up "$(service_port "$name")" || fail "$name is down, run scripts/start-all.sh first"
done

mkdir -p "$RUN/logs"
for suite in test_pipeline test_retrieval; do
  log "running tests/$suite.py"
  status=0
  (cd "$ROOT/tests" && python3 -m unittest -v "$suite") >"$RUN/logs/$suite.log" 2>&1 || status=$?
  cat "$RUN/logs/$suite.log"
  [ "$status" = "0" ] || fail "$suite failed, see .run/logs/$suite.log"
done
log "all tests passed"
