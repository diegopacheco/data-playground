#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

log "java unit tests on Java 25"
(cd "$ROOT/java-service" && mvn -q -B test) || fail "java unit tests failed"
grep -h "Tests run" "$ROOT"/java-service/target/surefire-reports/*.txt
for project in python-service lab; do
  log "$project unit tests and type check"
  (cd "$ROOT/$project" && uv run pytest -q) || fail "$project unit tests failed"
  (cd "$ROOT/$project" && uv run ty check) || fail "ty check $project failed"
done
log "e2e type check"
(cd "$ROOT/e2e" && uv run ty check) || fail "ty check e2e failed"

cluster_exists || fail "cluster $CLUSTER missing, run scripts/setup.sh first"
port_up "$(service_port lab)" || fail "lab is not forwarded, run scripts/start-all.sh first"

log "end-to-end tests on kind: delivery, scale to zero and back"
(cd "$ROOT/e2e" && e2e_env uv run pytest -v) || fail "end-to-end tests failed"
log "all tests passed"
