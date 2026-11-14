#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

log "python etl unit tests"
(cd "$ROOT/etl-python" && uv run pytest -q) || fail "python unit tests failed"
log "python etl type check"
(cd "$ROOT/etl-python" && uv run ty check) || fail "ty check etl-python failed"
log "e2e type check"
(cd "$ROOT/e2e" && uv run ty check) || fail "ty check e2e failed"
log "java etl unit tests on Java 25"
(cd "$ROOT/etl-java" && mvn -q -B test) || fail "java unit tests failed"
grep -h "Tests run" "$ROOT"/etl-java/target/surefire-reports/*.txt

cluster_exists || fail "cluster $CLUSTER missing, run scripts/setup.sh first"
kueue_ready || fail "kueue is not running, run scripts/setup.sh first"
[ -n "$(k get clusterqueue reports-cq --no-headers 2>/dev/null || true)" ] || fail "queues missing, run scripts/start-all.sh first"

log "end-to-end kueue tests on kind"
(cd "$ROOT/e2e" && e2e_env uv run pytest -v) || fail "end-to-end tests failed"
[ -s "$RUN/admission-report.md" ] && cat "$RUN/admission-report.md"
log "all tests passed"
