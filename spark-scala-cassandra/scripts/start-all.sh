#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require podman
require podman-compose
log "starting"

if ! podman image exists p1-spark-app; then
  podman-compose build pipeline
fi

podman-compose up -d cassandra
wait_port_up "$(service_port cassandra)" 60 || fail "cassandra did not open port $(service_port cassandra)"
wait_cassandra || fail "cassandra did not accept cql queries"
log "cassandra up on $(service_url cassandra)"

podman rm -f p1-pipeline >/dev/null 2>&1 || true
podman-compose up -d pipeline
code="$(podman wait p1-pipeline)"
podman logs p1-pipeline >"$LOGS/pipeline.log" 2>&1
[ "$code" = "0" ] || fail "pipeline failed with exit code $code, see $LOGS/pipeline.log"
log "pipeline finished, log at $LOGS/pipeline.log"

podman-compose up -d ui
wait_http "$(service_url ui)/api/revenue" 60 || fail "ui did not answer on $(service_url ui)/api/revenue"
log "ui up on $(service_url ui)"

"$SCRIPTS/status.sh"

log "links"
for name in $(service_names); do
  printf "%-14s %s\n" "$name" "$(service_url "$name")"
done
printf "%-14s %s\n" "api" "$(service_url ui)/api/revenue"
