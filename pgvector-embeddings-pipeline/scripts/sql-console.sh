#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

port_up "$(service_port postgres)" || fail "postgres is down, run scripts/start-all.sh first"
podman exec -it i48-postgres psql -U catalog -d catalog "$@"
