#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require podman-compose
require curl

curl -sf "$(service_url lakekeeper)/health" >/dev/null 2>&1 || fail "lakekeeper is down, run scripts/start-all.sh first"
log "rerunning the pipeline: bootstrap check, warehouse check, purge and rewrite shop.orders"
compose run -T --rm q4-pipeline || fail "pipeline failed"
