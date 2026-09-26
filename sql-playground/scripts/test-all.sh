#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

log "tests started"
require npm
port_up "$(service_port backend)" || fail "backend is not running on $(service_port backend), run ./scripts/start-all.sh first"
case "$(seed_status)" in
  *'"phase":"ready"'*) ;;
  *) fail "database is still seeding, wait for $(service_url backend) to report ready" ;;
esac

( cd "$ROOT" && npm test ) || fail "backend tests failed"
( cd "$ROOT" && npx vite build >"$LOGS/build.log" 2>&1 ) || fail "frontend build failed, see $LOGS/build.log"

log "tests passed"
