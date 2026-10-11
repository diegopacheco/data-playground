#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

stop_bg ui
stop_bg pipeline

if command -v podman-compose >/dev/null 2>&1; then
  podman-compose down >/dev/null 2>&1 || fail "podman-compose down failed"
fi
wait_port_down "$(service_port kafka)" 30 || fail "kafka port $(service_port kafka) still open"
log "kafka stopped"
