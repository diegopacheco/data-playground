#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

ui_ready >/dev/null || fail "ui is not running, run scripts/start-all.sh first"

log "source row counts"
curl -sf "$(service_url ui)/api/sources" | python3 -c 'import sys,json;[print("  " + s["table"] + ": " + str(s["rows"])) for s in json.load(sys.stdin)["sources"]]'

log "explain plan has one scan per connector"
plan="$(curl -sf "$(service_url ui)/api/explain")"
for catalog in postgres cassandra iceberg; do
  printf "%s" "$plan" | grep -q "table = $catalog:" || fail "explain plan has no scan for catalog $catalog"
  log "  scan found for $catalog"
done

log "federated result vs independent python join over the csv files"
UI_URL="$(service_url ui)" python3 "$ROOT/app/verify.py"
