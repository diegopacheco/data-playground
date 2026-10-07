#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require podman-compose
[ -x "$VENV/bin/dbt" ] || fail "virtualenv missing, run ./scripts/setup.sh first"
[ -f "$ROOT/jars/$ICEBERG_JAR" ] || fail "iceberg jar missing, run ./scripts/setup.sh first"

print_links() {
  log "links"
  printf "%-10s %s\n" thrift "$(service_url thrift)"
  printf "%-10s %s\n" spark_ui "$(service_url spark_ui)"
  printf "%-10s %s\n" ui "$(service_url ui)"
  printf "%-10s %s\n" api "$(service_url ui)/api/revenue"
}

if port_up "$(service_port thrift)" && port_up "$(service_port ui)"; then
  log "already running"
  print_links
  exit 0
fi

log "starting spark thrift server"
compose up -d thrift >/dev/null || fail "podman-compose up failed"
wait_port_up "$(service_port thrift)" 60 || fail "thrift did not open port $(service_port thrift)"
wait_until 60 thrift_ready || fail "thrift server did not answer queries, see: podman logs $THRIFT_CONTAINER"
log "thrift up on $(service_url thrift)"

log "dbt: reset namespace analytics"
dbt run-operation reset_schema || fail "reset_schema failed"
log "dbt: seed orders"
dbt seed || fail "dbt seed failed"
log "dbt: run 1 with orders up to $CUTOFF"
dbt run --vars "{cutoff: \"$CUTOFF\"}" || fail "dbt run 1 failed"
log "dbt: run 2 with all orders, fct_orders merges the new rows"
dbt run || fail "dbt run 2 failed"

log "starting ui"
start_bg ui "$ROOT/app" "$VENV/bin/python" server.py
wait_port_up "$(service_port ui)" 60 || fail "ui did not open port $(service_port ui), see $LOGS/ui.log"

log "fct_orders iceberg snapshots"
curl -sf "$(service_url ui)/api/snapshots" | "$VENV/bin/python" -c 'import json,sys
for s in json.load(sys.stdin): print(s["snapshot_id"], s["committed_at"], s["operation"], "added="+str(s["added_records"]), "deleted="+str(s["deleted_records"]), "total="+str(s["total_records"]))' || fail "could not read snapshots"

"$SCRIPTS/status.sh" || true
print_links
