#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require podman
port_up "$(service_port postgres)" || fail "postgres is down, run scripts/start-all.sh first"
if [ -t 0 ]; then
  exec podman exec -it r11-pglake psql -U postgres "$@"
fi
exec podman exec -i r11-pglake psql -U postgres "$@"
