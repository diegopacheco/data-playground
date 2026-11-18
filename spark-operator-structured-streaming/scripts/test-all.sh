#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

log "java job unit tests on JDK 25 (bytecode release 21)"
(cd "$ROOT/java-job" && mvn -q -B test) || fail "java unit tests failed"
grep -h "Tests run" "$ROOT"/java-job/target/surefire-reports/*.txt
log "python job unit tests on Python 3.14 with the Spark runtime JDK 21"
(cd "$ROOT/python-job" && JAVA_HOME="$JAVA21_HOME" uv run pytest -q -p no:cacheprovider) || fail "python job unit tests failed"
(cd "$ROOT/python-job" && uv run ty check) || fail "ty check python-job failed"
log "producer unit tests on Python 3.15"
(cd "$ROOT/producer" && uv run pytest -q) || fail "producer unit tests failed"
(cd "$ROOT/producer" && uv run ty check) || fail "ty check producer failed"
log "e2e type check"
(cd "$ROOT/e2e" && uv run ty check) || fail "ty check e2e failed"

cluster_exists || fail "cluster $CLUSTER missing, run scripts/setup.sh first"
for app in $APPS; do
  app_running "$app" || fail "$app is not RUNNING, run scripts/start-all.sh first"
done

log "end-to-end exactly-once and trigger sweep tests on kind"
rm -f "$RUN/results.tsv"
(cd "$ROOT/e2e" && KUBE_CONTEXT="$CTX" RESULTS_FILE="$RUN/results.tsv" uv run pytest -v) || fail "end-to-end tests failed"
log "measured results"
column -t -s "$(printf '\t')" "$RUN/results.tsv"
log "all tests passed"
