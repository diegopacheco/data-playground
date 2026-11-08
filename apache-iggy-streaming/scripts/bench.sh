#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

cluster_exists || fail "cluster $CLUSTER missing, run scripts/setup.sh first"
broker_ready iggy || fail "iggy is not running, run scripts/start-all.sh first"
broker_ready kafka || fail "kafka is not running, run scripts/start-all.sh first"
(cd "$ROOT/e2e" && e2e_env uv run python -m bench_e2e.bench "${1:-15}") || fail "benchmark failed"
