#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

log "tests started"

java25 mvn -q -B test || fail "java tests failed"
log "java tests passed"

[ -x "$VENV/bin/python" ] || fail "client venv missing, run ./scripts/setup.sh first"
curl -sf "http://localhost:$HTTP_PORT/health" >/dev/null || fail "flight server is down, run ./scripts/start-all.sh first"
( cd "$ROOT/client" && "$VENV/bin/python" -m pytest -q tests ) || fail "python flight tests failed"

log "tests passed"
