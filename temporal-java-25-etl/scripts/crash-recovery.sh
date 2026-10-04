#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

workflow_id="${1:-etl-crash-$(date +%Y%m%d-%H%M%S)}"
millis_per_order=150
kill_at=60

require java
[ -n "$(bg_pid worker)" ] || fail "worker is not running, run ./scripts/start-all.sh first"

progress_reached() {
  grep "transformAggregate workflow=$workflow_id " "$LOGS/worker.log" | grep -Eo 'progress=[0-9]+' | cut -d= -f2 | awk -v k="$kill_at" '$1>=k{f=1} END{exit f?0:1}'
}

log "starting workflow $workflow_id with a slow heartbeating transform"
starter start "$workflow_id" "$ORDERS_CSV" 1 "$millis_per_order"

wait_until 60 progress_reached || fail "transform never reached $kill_at orders, see $LOGS/worker.log"
old_pid="$(bg_pid worker)"
cp "$LOGS/worker.log" "$LOGS/worker-crashed-$old_pid.log"
log "transform passed $kill_at orders, killing worker pid $old_pid with SIGKILL"
kill -KILL "$old_pid"
wait_until 10 sh -c "! kill -0 $old_pid" || fail "worker pid $old_pid is still alive"
rm -f "$RUN/worker.pid"

log "restarting worker"
start_worker

log "waiting for $workflow_id to finish on the new worker"
starter wait "$workflow_id" || fail "workflow $workflow_id did not complete after the crash"
