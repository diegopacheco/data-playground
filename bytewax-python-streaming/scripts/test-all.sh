#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

log "tests started"

require curl
require python3
[ -x "$FLOW_PY" ] || fail "dataflow venv missing, run ./scripts/setup.sh first"

log "unit tests"
"$FLOW_PY" -m unittest discover -s "$ROOT/tests" -v || fail "unit tests failed"

port_up "$(service_port redpanda)" || fail "redpanda is not running, run ./scripts/start-all.sh first"
port_up "$(service_port ui)" || fail "ui is not running, run ./scripts/start-all.sh first"

api() {
  curl -sf "$(service_url ui)/api/$1"
}

rows="$(tail -n +2 "$CSV" | wc -l | tr -d ' ')"
split=120

log "integration: crash and resume with recovery"
stop_dataflow TERM
recreate_topics
reset_state

produce_rows 1 "$split"
start_dataflow
wait_for 60 store_has "$split" || fail "first run did not reach $split orders, see $LOGS/dataflow.log"
log "first run reached $(store_orders) orders, waiting for a recovery snapshot"
pause_seconds 3
stop_dataflow KILL

produce_rows "$((split + 1))" "$rows"
start_dataflow
wait_for 60 store_has "$rows" || fail "resumed run did not reach $rows orders, got $(store_orders)"
log "resumed run reached $(store_orders) orders"

expected_totals="$(tail -n +2 "$CSV" | awk -F, '{o[$4]++; q[$4]+=$5; r[$4]+=$5*$6} END {for (c in o) printf "%s %d %d %.2f\n", c, o[c], q[c], r[c]}' | sort)"
expected_windows="$(tail -n +2 "$CSV" | awk -F, '{d=substr($7,1,10); k=$4" "d; o[k]++; q[k]+=$5; r[k]+=$5*$6; if (d>last[$4]) last[$4]=d} END {for (k in o) {split(k,p," "); if (p[2]!=last[p[1]]) printf "%s %s %d %d %.2f\n", p[1], p[2], o[k], q[k], r[k]}}' | sort)"
window_count="$(printf "%s\n" "$expected_windows" | wc -l | tr -d ' ')"

windows_settled() {
  [ "$(api windows | python3 -c 'import json,sys; print(len(json.load(sys.stdin)))')" = "$window_count" ]
}
wait_for 30 windows_settled || fail "expected $window_count closed windows"

actual_totals="$(api totals | python3 -c 'import json,sys
for r in json.load(sys.stdin): print(r["category"], r["orders"], r["quantity"], "%.2f" % (r["revenue_cents"] / 100))' | sort)"
actual_windows="$(api windows | python3 -c 'import json,sys
for r in json.load(sys.stdin): print(r["category"], r["window_start"][:10], r["orders"], r["quantity"], "%.2f" % (r["revenue_cents"] / 100))' | sort)"

out_size="$(topic_size "$OUT_TOPIC")"
topic_totals="$(rpk topic consume "$OUT_TOPIC" --offset start -n "$out_size" -f '%v\n' | python3 -c 'import json,sys
last = {}
for line in sys.stdin:
    r = json.loads(line)
    if r["kind"] == "total": last[r["category"]] = r
for r in last.values(): print(r["category"], r["orders"], r["quantity"], "%.2f" % (r["revenue_cents"] / 100))' | sort)"

log "expected totals from awk"
log "$expected_totals"
log "actual totals from store"
log "$actual_totals"
log "latest totals from topic $OUT_TOPIC ($out_size messages)"
log "$topic_totals"
log "closed windows: expected $window_count, store has $(printf "%s\n" "$actual_windows" | wc -l | tr -d ' ')"
log "dataflow runs"
api runs | python3 -c 'import json,sys
for r in json.load(sys.stdin): print("run", r["run_id"], "events", r["events"])'

[ "$(printf "%s\n" "$actual_totals" | wc -l | tr -d ' ')" = "6" ] || fail "expected 6 categories"
[ "$expected_totals" = "$actual_totals" ] || fail "store totals do not match awk"
[ "$expected_totals" = "$topic_totals" ] || fail "output topic totals do not match awk"
[ "$expected_windows" = "$actual_windows" ] || fail "closed windows do not match awk"
second_run_events="$(api runs | python3 -c 'import json,sys; print(json.load(sys.stdin)[-1]["events"])')"
[ "$second_run_events" -lt "$rows" ] || fail "resumed run reprocessed the whole topic ($second_run_events events)"
[ "$second_run_events" -ge "$((rows - split))" ] || fail "resumed run skipped orders ($second_run_events events)"

log "tests passed"
