#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

pinot_ready >/dev/null 2>&1 || fail "pinot is not running, run ./scripts/start-all.sh first"

if [ "$#" -gt 0 ]; then
  pinot_sql "$*"
  exit 0
fi

log "pinot broker sql on $(service_url pinot-broker), one statement per line, empty line or ctrl-d to quit"
while IFS= read -r -p "pinot> " sql; do
  [ -n "$sql" ] || break
  pinot_sql "$sql" || true
done
