#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

fail_attempts="${1:-2}"
millis_per_order="${2:-5}"
workflow_id="${3:-etl-$(date +%Y%m%d-%H%M%S)}"

require java
[ -d "$ROOT/target/lib" ] || build_app
[ -n "$(bg_pid worker)" ] || fail "worker is not running, run ./scripts/start-all.sh first"

log "running workflow $workflow_id failExtractAttempts=$fail_attempts millisPerOrder=$millis_per_order"
starter run "$workflow_id" "$ORDERS_CSV" "$fail_attempts" "$millis_per_order" || fail "workflow $workflow_id failed"
