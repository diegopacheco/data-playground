#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

[ "$(container_state t6-console)" = "running" ] || fail "t6-console is not running, run scripts/start-all.sh first"
log "sql console on the primary $(service_url primary), one statement per line, ctrl-d to quit"
if [ -t 0 ]; then
  podman exec -it t6-console node app/sql.js
else
  podman exec -i t6-console node app/sql.js
fi
