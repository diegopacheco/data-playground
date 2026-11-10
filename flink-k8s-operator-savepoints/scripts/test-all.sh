#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

log "java job unit tests on Java 25 (bytecode release 21)"
(cd "$ROOT/java-job" && mvn -q -B test) || fail "java unit tests failed"
grep -h "Tests run" "$ROOT"/java-job/target/surefire-reports/*.txt
log "python job unit tests"
(cd "$ROOT/python-job" && uv run pytest -q) || fail "python unit tests failed"
log "python job type check"
(cd "$ROOT/python-job" && uv run ty check) || fail "ty check python-job failed"
log "e2e type check"
(cd "$ROOT/e2e" && uv run ty check) || fail "ty check e2e failed"

cluster_exists || fail "cluster $CLUSTER missing, run scripts/setup.sh first"
for job in $JOBS; do
  job_running "$job" || fail "$job is not RUNNING, run scripts/start-all.sh first"
done

log "end-to-end savepoint, rescale and stateless tests on kind"
(cd "$ROOT/e2e" && KUBE_CONTEXT="$CTX" RESULTS_FILE="$RUN/results.tsv" uv run pytest -v) || fail "end-to-end tests failed"
log "measured transitions"
column -t -s "$(printf '\t')" "$RUN/results.tsv"
log "all tests passed"
