#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require podman
require podman-compose
require curl
podman image exists "$APP_IMAGE" || fail "image $APP_IMAGE missing, run scripts/setup.sh first"
data_ready || fail "dataset missing, run scripts/setup.sh first"

log "starting spark connect and sail"
compose up -d r2-spark r2-sail >/dev/null 2>&1 || fail "podman-compose up r2-spark r2-sail failed"
wait_until 60 port_up "$(service_port sail)" || fail "sail not listening, see: podman logs r2-sail"
log "sail up on $(service_url sail)"
wait_until 60 spark_ready || fail "spark connect not ready, see: podman logs r2-spark"
log "spark connect up on $(service_url spark)"

log "starting ui"
compose up -d r2-app >/dev/null 2>&1 || fail "podman-compose up r2-app failed"
wait_until 60 curl -s -o /dev/null "$(service_url ui)/" || fail "ui did not answer, see: podman logs r2-app"
log "ui up on $(service_url ui)"

if [ -f "$ROOT/results/results.json" ]; then
  log "results/results.json exists, skipping benchmark (run scripts/bench.sh to rerun)"
else
  "$SCRIPTS/bench.sh"
fi

"$SCRIPTS/status.sh"

log "links"
printf "%-10s %s\n" ui "$(service_url ui)"
printf "%-10s %s\n" spark "$(service_url spark)"
printf "%-10s %s\n" sail "$(service_url sail)"
printf "%-10s %s\n" sparkui "$(service_url sparkui)"
printf "%-10s %s\n" results "$(service_url ui)/api/results"
