#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

port_up "$(service_port ui)" || fail "ui is not running on $(service_port ui), run ./scripts/start-all.sh first"

log "opening $(service_url ui)"
open_url "$(service_url ui)"
