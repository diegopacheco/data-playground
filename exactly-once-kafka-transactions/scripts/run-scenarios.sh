#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

mkdir -p "$LOGS"
rm -f "$RUN"/*.hold "$RUN"/*.fenced "$RUN/events.tsv"

start_worker() {
  nohup "${JAVA[@]}" eos.Worker "$1" "$2" "$3" >>"$LOGS/worker-$1.log" 2>&1 &
  pid=$!
  echo "$pid" >"$RUN/worker.pid"
  wait_until 60 test -f "$RUN/$1.hold" || fail "worker $1 never reached offset $3, see .run/logs/worker-$1.log"
}

drain() {
  "${JAVA[@]}" eos.Worker "$1" "$2" -1 >>"$LOGS/worker-$1.log" 2>&1 || fail "worker $1 did not drain, see .run/logs/worker-$1.log"
}

kill_scenario() {
  local offset
  for offset in $KILL_OFFSETS; do
    start_worker "$1" "$2" "$offset"
    event "$1" "SIGKILL worker pid $pid before commit, records sent up to offset $((offset - 1))"
    kill -9 "$pid"
    wait "$pid" 2>/dev/null || true
    rm -f "$RUN/$1.hold" "$RUN/worker.pid"
    log "$1: killed worker at offset $offset"
  done
  drain "$1" "$2"
  log "$1: restarted worker drained the input"
}

fence_scenario() {
  local code
  start_worker fencing transactional "$FENCE_OFFSET"
  event fencing "zombie pid $pid stays alive with an open transaction at offset $FENCE_OFFSET"
  drain fencing transactional
  event fencing "second instance finished, zombie resumes"
  rm -f "$RUN/fencing.hold"
  code=0
  wait "$pid" || code=$?
  rm -f "$RUN/worker.pid"
  [ "$code" -eq 3 ] || fail "zombie exited with $code instead of being fenced, see .run/logs/worker-fencing.log"
  log "fencing: zombie fenced with $(cat "$RUN/fencing.fenced")"
}

log "seeding input topics from data/payments.csv"
"${JAVA[@]}" eos.Seeder >"$LOGS/seeder.log" 2>&1 || fail "seeder failed, see .run/logs/seeder.log"
kill_scenario transactional transactional
kill_scenario at-least-once plain
fence_scenario
