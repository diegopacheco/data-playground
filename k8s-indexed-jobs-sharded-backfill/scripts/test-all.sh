#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

log "python worker unit tests"
(cd "$ROOT/python-worker" && uv run pytest -q) || fail "python unit tests failed"
log "python worker type check"
(cd "$ROOT/python-worker" && uv run ty check) || fail "ty check python-worker failed"
log "e2e type check"
(cd "$ROOT/e2e" && uv run ty check) || fail "ty check e2e failed"
log "java worker unit tests on Java 25 with --enable-preview"
(cd "$ROOT/java-worker" && mvn -q -B test) || fail "java unit tests failed"
grep -h "Tests run" "$ROOT"/java-worker/target/surefire-reports/*.txt

port_up "$(service_port postgres)" || fail "postgres is DOWN, run scripts/start-all.sh first"

log "end-to-end indexed job tests on kind"
(cd "$ROOT/e2e" && KUBE_CONTEXT="$CTX" PG_PORT="$(service_port postgres)" PY_IMAGE="$PY_IMAGE" JAVA_IMAGE="$JAVA_IMAGE" \
  uv run pytest -v) || fail "end-to-end tests failed"
log "all tests passed"
