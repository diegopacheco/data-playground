#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

log "starting"

require podman-compose
require python3
[ -x "$FLOW_PY" ] || fail "dataflow venv missing, run ./scripts/setup.sh first"

podman-compose up -d
wait_port_up "$(service_port redpanda)" 60 || fail "redpanda did not open port $(service_port redpanda)"
wait_for 60 redpanda_ready || fail "redpanda is not healthy"
wait_for 30 relax_disk_limit || fail "could not set storage_min_free_bytes"
log "redpanda up on $(service_url redpanda)"

wait_for 30 ensure_topics || fail "could not create topics"
if [ "$(topic_size "$IN_TOPIC")" = "0" ]; then
  rows="$(tail -n +2 "$CSV" | wc -l | tr -d ' ')"
  produce_rows 1 "$rows"
fi

start_dataflow

start_bg ui "$ROOT/ui" python3 server.py
wait_port_up "$(service_port ui)" 30 || fail "ui did not open port $(service_port ui), see $LOGS/ui.log"
log "ui up on $(service_url ui)"

"$SCRIPTS/status.sh"

log "links"
for name in $(service_names); do
  printf "%-10s %s\n" "$name" "$(service_url "$name")"
done
printf "%-10s %s\n" "api" "$(service_url ui)/api/totals"
