#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require podman
require podman-compose
require curl
podman image exists "$APP_IMAGE" || fail "image $APP_IMAGE missing, run scripts/setup.sh first"

log "starting redpanda and postgres"
compose up -d r13-redpanda r13-postgres >/dev/null 2>&1 || fail "podman-compose up r13-redpanda r13-postgres failed"
wait_until 60 redpanda_ready || fail "redpanda not healthy, see: podman logs r13-redpanda"
log "redpanda up on $(service_url redpanda)"
wait_until 60 postgres_ready || fail "postgres not ready, see: podman logs r13-postgres"
log "postgres up on $(service_url postgres)"

log "starting app"
compose up -d r13-app >/dev/null 2>&1 || fail "podman-compose up r13-app failed"
wait_until 60 curl -sf -o /dev/null "$(service_url ui)/" || fail "app did not answer, see: podman logs r13-app"
log "app up on $(service_url ui)"

if scenario_ready; then
  log "scenario already ran, skipping (POST /api/scenario to rerun)"
else
  log "running the kappa vs lambda scenario"
  run_scenario
  log "scenario passed every check"
fi

"$SCRIPTS/status.sh"

log "links"
printf "%-10s %s\n" ui "$(service_url ui)"
printf "%-10s %s\n" scenario "$(service_url ui)/api/scenario"
printf "%-10s %s\n" state "$(service_url ui)/api/state"
printf "%-10s %s\n" redpanda "$(service_url redpanda)"
printf "%-10s %s\n" postgres "$(service_url postgres)"
