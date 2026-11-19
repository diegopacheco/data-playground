#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

log "producer unit tests (java 25)"
(cd "$ROOT/producer" && mvn -q -B test) || fail "producer unit tests failed"

log "consumer unit tests and type check (python 3.15)"
(cd "$ROOT/consumer" && uv run -q pytest -q && uv run -q ty check) || fail "consumer tests or ty failed"

log "e2e harness unit tests and type check"
(cd "$ROOT/e2e" && uv run -q pytest -q tests/test_topology.py && uv run -q ty check) || fail "e2e harness tests or ty failed"

port_up "$(service_port producer)" || fail "producer is DOWN, run scripts/start-all.sh first"

log "end to end tests on kind: rolling restart without loss, then partition reassignment with cruise control"
(cd "$ROOT/e2e" && PRODUCER_URL="http://localhost:$(service_port producer)" KUBE_CONTEXT="$CTX" KAFKA_NAMESPACE="$NS" \
  uv run -q pytest -v -s tests/cluster 2>&1 | tee "$RUN/logs/e2e.log") || fail "end to end tests failed, see $RUN/logs/e2e.log"
grep '^RESULT\|^  ' "$RUN/logs/e2e.log" > "$RUN/results.txt" || true
log "all tests passed, results in .run/results.txt"
