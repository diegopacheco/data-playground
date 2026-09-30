#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require podman
for name in minio controller broker ui; do
  port_up "$(service_port "$name")" || fail "$name is down, run scripts/start-all.sh first"
done

"$SCRIPTS/proof.sh"

mkdir -p "$RUN/logs"
status=0
podman exec r9-app python -m unittest -v tests.test_diskless >"$RUN/logs/tests.log" 2>&1 || status=$?
cat "$RUN/logs/tests.log"
[ "$status" = "0" ] || fail "tests failed, see .run/logs/tests.log"
log "all tests passed"
