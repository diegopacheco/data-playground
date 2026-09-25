#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require podman-compose

log "starting cassandra"
compose up -d p5-cassandra >/dev/null
wait_port_up "$(service_port cassandra)" 60 || fail "cassandra did not open port $(service_port cassandra)"
wait_until 60 cql_ready || fail "cassandra did not accept cql in time, see: podman logs p5-cassandra"
log "cassandra up on $(service_url cassandra)"

log "running dbt seed, run, test and loading into cassandra"
compose run --rm p5-pipeline || fail "pipeline failed"

log "starting ui"
compose up -d p5-ui >/dev/null
wait_port_up "$(service_port ui)" 60 || fail "ui did not open port $(service_port ui)"
wait_until 60 curl -sf "$(service_url ui)/api/revenue" || fail "ui api did not answer, see: podman logs p5-ui"
log "ui up on $(service_url ui)"

"$SCRIPTS/status.sh"

log "links"
printf "%-14s %s\n" cassandra "$(service_url cassandra)"
printf "%-14s %s\n" ui "$(service_url ui)"
printf "%-14s %s\n" api "$(service_url ui)/api/revenue"
