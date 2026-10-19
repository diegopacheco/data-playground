#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require podman
port_up "$(service_port redis)" || fail "redis is down, run scripts/start-all.sh first"
podman exec -it r16-redis redis-cli "$@"
