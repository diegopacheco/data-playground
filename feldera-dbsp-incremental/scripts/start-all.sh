#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require podman
require podman-compose
require curl
podman image exists "$APP_IMAGE" || fail "image $APP_IMAGE missing, run scripts/setup.sh first"
podman image exists "$FELDERA_IMAGE" || fail "image $FELDERA_IMAGE missing, run scripts/setup.sh first"
mkdir -p "$RUN/logs"

log "starting the feldera pipeline manager"
compose up -d t3-feldera >/dev/null 2>&1 || fail "podman-compose up t3-feldera failed"
wait_until 60 feldera_healthy || fail "feldera did not become healthy, see: podman logs t3-feldera"
log "feldera up on $(service_url feldera)"

log "starting ui"
compose up -d t3-app >/dev/null 2>&1 || fail "podman-compose up t3-app failed"
wait_until 60 curl -sf -o /dev/null "$(service_url ui)/" || fail "ui did not answer, see: podman logs t3-app"

log "creating, compiling (about 1 minute the first time) and starting pipeline incremental"
api_post deploy >"$RUN/logs/deploy.json" || fail "pipeline deploy failed, see .run/logs/deploy.json and podman logs t3-feldera"
grep -q '"deployment_status": "Running"' "$RUN/logs/deploy.json" || fail "pipeline not running, see .run/logs/deploy.json"
log "pipeline incremental running"

if [ "$(api results)" = "{}" ]; then
  log "running the scaling and changes scenarios once"
  api_post run-all >/dev/null || fail "scenarios failed, see: podman logs t3-app"
fi

"$SCRIPTS/status.sh"

log "links"
for name in $(service_names); do
  printf "%-10s %s\n" "$name" "$(service_url "$name")"
done
printf "%-10s %s\n" api "$(service_url feldera)/v0/pipelines/incremental"
printf "%-10s %s\n" results "$(service_url ui)/api/results"
