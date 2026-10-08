#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

port_up "$UI_PORT" || fail "ui is not running on $UI_PORT, run ./scripts/start-all.sh first"

log "opening $(service_url ui)"
open_url "$(service_url ui)"
