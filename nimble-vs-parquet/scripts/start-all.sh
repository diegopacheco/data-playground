#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require podman
require podman-compose
require curl
podman image exists "$APP_IMAGE" || fail "image $APP_IMAGE missing, run scripts/setup.sh first"

if [ "${RERUN:-0}" = "1" ] || ! lake_ready; then
  "$SCRIPTS/bench.sh"
else
  log "results and lake volume present, skipping benchmark (RERUN=1 to run again)"
fi

log "starting ui"
compose up -d t9-ui >/dev/null 2>&1 || fail "podman-compose up t9-ui failed"
wait_until 60 curl -sf "$(service_url ui)/api/health" || fail "ui did not answer, see: podman logs t9-ui"
log "ui up on $(service_url ui)"

"$SCRIPTS/status.sh"

log "links"
printf "%-10s %s\n" ui "$(service_url ui)"
printf "%-10s %s\n" results "$(service_url ui)/api/results"
printf "%-10s %s\n" project "$(service_url ui)/api/project?table=wide&count=5"
printf "%-10s %s\n" meta "$(service_url ui)/api/meta?table=wide"
