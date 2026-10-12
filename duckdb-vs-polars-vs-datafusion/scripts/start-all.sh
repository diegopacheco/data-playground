#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require_setup
[ -f "$ROOT/results.json" ] || run_bench
export PORT="$(service_port ui)"
start_bg ui "$ROOT" "$PY" "$ROOT/src/server.py"
wait_port_up "$(service_port ui)" || fail "ui did not open port $(service_port ui), see $LOGS/ui.log"
log "ui: $(service_url ui)"
log "api: $(service_url ui)/api/results"
