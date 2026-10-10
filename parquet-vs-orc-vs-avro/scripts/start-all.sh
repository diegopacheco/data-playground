#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

PY="$ROOT/.venv/bin/python"
[ -x "$PY" ] || fail "virtualenv missing, run ./scripts/setup.sh first"

if [ ! -f "$ROOT/results/results.json" ] || [ "${RERUN:-0}" = "1" ]; then
  log "running benchmark rows=${ROWS:-1000000} iterations=${ITERATIONS:-5}"
  "$PY" "$ROOT/app/bench.py" || fail "benchmark failed"
else
  log "results/results.json present, set RERUN=1 to benchmark again"
fi

export UI_PORT="$(service_port ui)"
start_bg ui "$ROOT/app" "$PY" server.py
wait_port_up "$(service_port ui)" 60 || fail "ui did not open port $(service_port ui), see $LOGS/ui.log"
log "ui up on $(service_url ui)"

"$SCRIPTS/status.sh"

log "links"
printf "%-14s %s\n" ui "$(service_url ui)"
printf "%-14s %s\n" api "$(service_url ui)/api/results"
