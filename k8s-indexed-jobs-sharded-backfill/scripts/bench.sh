#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

port_up "$(service_port postgres)" || fail "postgres is DOWN, run scripts/start-all.sh first"
(cd "$ROOT/e2e" && KUBE_CONTEXT="$CTX" PG_PORT="$(service_port postgres)" PY_IMAGE="$PY_IMAGE" JAVA_IMAGE="$JAVA_IMAGE" \
  uv run python -m backfill_e2e.bench "${1:-3}") || fail "benchmark failed"
