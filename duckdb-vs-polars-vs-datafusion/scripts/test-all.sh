#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require_setup
run_bench
"$PY" "$ROOT/tests/test_results.py" || fail "result verification failed"
