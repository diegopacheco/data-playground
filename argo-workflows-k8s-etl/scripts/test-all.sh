#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require python3
log "unit tests on host python3"
python3 -m unittest -v tests.test_steps || fail "unit tests failed"

for name in argo_ui etl_ui; do
  port_up "$(service_port "$name")" || fail "$name is DOWN, run scripts/start-all.sh first"
done

log "workflow integration tests against $(service_url argo_ui)"
ARGO_URL="$(service_url argo_ui)" UI_URL="$(service_url etl_ui)" KUBE_CONTEXT="$CTX" NAMESPACE="$NAMESPACE" \
  python3 -m unittest -v tests.test_workflow || fail "workflow integration tests failed"
log "all tests passed"
