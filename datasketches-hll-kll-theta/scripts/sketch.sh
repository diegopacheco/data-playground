#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require podman
port_up "$(service_port ui)" || fail "ui is down, run scripts/start-all.sh first"

mkdir -p "$RUN/logs"
log "building sketches per partition, merging them and computing exact answers"
podman exec r17-app python app/sketches.py >"$RUN/logs/sketch.log" 2>&1 || fail "sketching failed, see .run/logs/sketch.log"
cat "$RUN/logs/sketch.log"
