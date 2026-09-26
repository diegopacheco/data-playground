#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require podman
port_up "$(service_port spark)" || fail "spark is down, run scripts/start-all.sh first"
port_up "$(service_port sail)" || fail "sail is down, run scripts/start-all.sh first"

mkdir -p "$RUN/logs"
log "running the benchmark with ${BENCH_RUNS:-5} warm runs per query, same pyspark client against spark and sail"
status=0
podman exec -e "BENCH_RUNS=${BENCH_RUNS:-5}" r2-app python app/bench.py 2>&1 | grep -v -e FutureWarning -e require_minimum | tee "$RUN/logs/bench.log" || status=$?
[ "$status" = "0" ] || fail "benchmark failed, see .run/logs/bench.log"
