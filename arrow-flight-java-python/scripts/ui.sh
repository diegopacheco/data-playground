#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

url="$(service_url ui)"
port_up "$UI_PORT" || fail "ui is not running on $UI_PORT, run ./scripts/start-all.sh first"

log "opening $url"
open_url "$url"
