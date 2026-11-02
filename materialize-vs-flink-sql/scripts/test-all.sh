#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require podman
for name in ui mzsql kafka gateway; do
  port_up "$(service_port "$name")" || fail "$name is down, run scripts/start-all.sh first"
done

mkdir -p "$RUN/logs"
log "running a fresh comparison: new topics, materialize views, ingestion with probes, flink queries"
api_post run >/dev/null || fail "comparison run failed, see: podman logs t2-app"

status=0
podman exec t2-app python -m unittest -v tests.test_engines >"$RUN/logs/tests.log" 2>&1 || status=$?
cat "$RUN/logs/tests.log"
[ "$status" = "0" ] || fail "tests failed, see .run/logs/tests.log"
log "all tests passed"
