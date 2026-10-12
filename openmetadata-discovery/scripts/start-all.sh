#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require podman
require podman-compose
require curl
require python3
podman image exists "$APP_IMAGE" || fail "image $APP_IMAGE missing, run scripts/setup.sh first"
mkdir -p "$RUN/logs"

log "starting postgres, elasticsearch, openmetadata migrations, openmetadata server and the app"
compose up -d >"$RUN/logs/compose.log" 2>&1 || fail "podman-compose up failed, see .run/logs/compose.log"
[ "$(podman inspect -f '{{.State.ExitCode}}' r14-migrate 2>/dev/null || echo 1)" = "0" ] || fail "openmetadata migrations failed, see: podman logs r14-migrate"
wait_until 60 om_up || fail "openmetadata did not answer on $(service_url openmetadata), see: podman logs r14-openmetadata"
log "openmetadata $(om_up | json_field version) up on $(service_url openmetadata)"
wait_until 60 api status || fail "app did not answer on $(service_url ui), see: podman logs r14-app"

if [ "$(api verify | json_field ok)" != "True" ]; then
  log "catalog does not match postgres and curation.json yet, running ingestion and curation"
  curl -sf -m 300 -X POST "$(service_url ui)/api/ingest" >"$RUN/logs/ingest.json" || fail "ingestion failed, see .run/logs/ingest.json and: podman logs r14-app"
  log "ingestion done in $(json_field seconds <"$RUN/logs/ingest.json") s"
else
  log "catalog already matches postgres and curation.json ($(api verify | json_field passed) checks), skipping ingestion"
fi

"$SCRIPTS/status.sh"

log "links"
printf "%-14s %s\n" ui "$(service_url ui)"
printf "%-14s %s\n" openmetadata "$(service_url openmetadata)"
printf "%-14s %s\n" postgres "$(service_url postgres)"
printf "%-14s %s\n" catalog "$(service_url ui)/api/catalog"
printf "%-14s %s\n" lineage "$(service_url ui)/api/lineage"
printf "%-14s %s\n" search "$(service_url ui)/api/search?q=revenue"
printf "%-14s %s\n" verify "$(service_url ui)/api/verify"
