#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

log "setup started"
require podman
require podman-compose
require node
require npm

mkdir -p "$ROOT/tmp/pgdata"
compose pull
( cd "$ROOT" && npm install )

if [ -f "$ROOT/.gitignore" ] && ! grep -q '^\.run/$' "$ROOT/.gitignore"; then
  printf ".run/\n" >>"$ROOT/.gitignore"
fi

log "setup done, database files live in $ROOT/tmp/pgdata"
