#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require podman-compose
port_up "$(service_port postgres)" || fail "postgres is down, run ./scripts/start-all.sh first"

log "running beam pipeline on the DirectRunner"
compose run --rm q2-pipeline >"$LOGS/pipeline.log" 2>&1 || fail "beam pipeline failed, see $LOGS/pipeline.log"
grep "beam pipeline wrote" "$LOGS/pipeline.log" || fail "beam pipeline did not finish, see $LOGS/pipeline.log"
