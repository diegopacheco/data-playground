#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

log "setup started"
require podman
require podman-compose
require python3
podman pull -q docker.io/library/cassandra:5.0.9 >/dev/null
podman-compose build >"$LOGS/build.log" 2>&1 || fail "image build failed, see $LOGS/build.log"

if [ ! -f "$ROOT/.gitignore" ] || ! grep -q '^\.run/$' "$ROOT/.gitignore"; then
  printf ".run/\n" >>"$ROOT/.gitignore"
fi

log "setup done"
