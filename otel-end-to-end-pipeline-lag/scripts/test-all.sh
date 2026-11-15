#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

log "producer unit tests (java 25)"
(cd "$ROOT/producer" && mvn -q -B test) || fail "producer unit tests failed"

log "consumer unit tests and type check (python 3.15)"
(cd "$ROOT/consumer" && uv run -q pytest -q && uv run -q ty check) || fail "consumer tests or ty failed"

log "e2e harness unit tests and type check"
(cd "$ROOT/e2e" && uv run -q pytest -q --ignore=tests/cluster && uv run -q ty check) || fail "e2e harness tests or ty failed"

log "prometheus slo and burn rate rule tests (promtool)"
podman run --rm -v "$ROOT/k8s/prometheus:/rules:ro" -w /rules --entrypoint promtool "$PROMETHEUS_IMAGE" \
  test rules rules_test.yml || fail "promtool rule tests failed"

for name in producer prometheus jaeger; do
  port_up "$(service_port "$name")" || fail "$name is DOWN, run scripts/start-all.sh first"
done

log "end to end tests on kind: trace propagation, lag histogram vs sink rows, slowdown fires fast burn and recovers"
(cd "$ROOT/e2e" && PRODUCER_URL="$(service_base producer)" PROMETHEUS_URL="$(service_base prometheus)" \
  JAEGER_URL="$(service_base jaeger)" KUBE_CONTEXT="$CTX" PIPELINE_NAMESPACE="$NS" \
  uv run -q pytest -v -s tests/cluster 2>&1 | tee "$RUN/logs/e2e.log") || fail "end to end tests failed, see $RUN/logs/e2e.log"
grep '^RESULT\|^  ' "$RUN/logs/e2e.log" > "$RUN/results.txt" || true
log "all tests passed, results in .run/results.txt"
