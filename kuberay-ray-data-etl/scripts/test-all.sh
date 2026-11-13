#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

log "producer unit tests on Java 25"
(cd "$ROOT/producer" && mvn -q -B test) || fail "producer unit tests failed"
grep -h "Tests run" "$ROOT"/producer/target/surefire-reports/*.txt
log "etl unit tests on Python 3.14 with a local Ray"
(cd "$ROOT/etl" && uv run pytest -q -p no:warnings) || fail "etl unit tests failed"
log "etl type check"
(cd "$ROOT/etl" && uv run ty check) || fail "ty check etl failed"
log "e2e type check"
(cd "$ROOT/e2e" && uv run ty check) || fail "ty check e2e failed"

cluster_exists || fail "cluster $CLUSTER missing, run scripts/setup.sh first"
ray_job_running || fail "rayjob etl-driver is not running, run scripts/start-all.sh first"
port_up "$(service_port minio-api)" || fail "minio-api port-forward is down, run scripts/start-all.sh first"

log "end-to-end exactly-once, autoscaling and worker kill tests on kind"
(cd "$ROOT/e2e" && KUBE_CONTEXT="$CTX" RESULTS_FILE="$RUN/results.md" uv run pytest -v) || fail "end-to-end tests failed"
log "measured results"
cat "$RUN/results.md"
log "all tests passed"
