#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

log "python bench unit tests"
(cd "$ROOT/python-bench" && uv run pytest -q) || fail "python unit tests failed"
log "python bench type check"
(cd "$ROOT/python-bench" && uv run ty check) || fail "ty check python-bench failed"
log "e2e type check"
(cd "$ROOT/e2e" && uv run ty check) || fail "ty check e2e failed"
log "java bench unit tests on Java 25"
(cd "$ROOT/java-bench" && mvn -q -B test) || fail "java unit tests failed"
grep -h "Tests run" "$ROOT"/java-bench/target/surefire-reports/*.txt

cluster_exists || fail "cluster $CLUSTER missing, run scripts/setup.sh first"
broker_ready iggy || fail "iggy is not running, run scripts/start-all.sh first"
broker_ready kafka || fail "kafka is not running, run scripts/start-all.sh first"

log "end-to-end streaming tests on kind"
(cd "$ROOT/e2e" && e2e_env uv run pytest -v) || fail "end-to-end tests failed"
log "all tests passed"
