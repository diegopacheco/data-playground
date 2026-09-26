#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

port_up "$(service_port postgres)" || fail "postgres is down, run scripts/start-all.sh first"
log "loading products.csv and orders.csv and building the ParadeDB indexes"
psql_exec -q -f /sql/load.sql || fail "load failed"
