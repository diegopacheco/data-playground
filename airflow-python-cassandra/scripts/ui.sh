#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

url="$(service_url ui)"
port_up "$(service_port ui)" || fail "ui is not running, run ./scripts/start-all.sh first"

log "opening $url"
open_url "$url"
