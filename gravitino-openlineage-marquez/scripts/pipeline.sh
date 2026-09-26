#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require podman-compose
port_up "$(service_port gravitino)" || fail "gravitino is down, run scripts/start-all.sh first"
port_up "$(service_port marquez)" || fail "marquez is down, run scripts/start-all.sh first"

log "registering metadata in gravitino, running raw -> clean -> revenue_by_category and emitting openlineage events"
compose run -T --rm r6-pipeline 2>/dev/null || fail "pipeline failed, see: podman-compose run --rm r6-pipeline"
