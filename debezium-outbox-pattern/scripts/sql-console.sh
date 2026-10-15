#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

port_up "$(service_port postgres)" || fail "postgres is down, run scripts/start-all.sh first"
exec podman exec -it s3-postgres psql -U s3 -d shop "$@"
