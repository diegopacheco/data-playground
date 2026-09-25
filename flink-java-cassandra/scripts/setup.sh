#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

log "setup started"

require podman
require podman-compose
require java
java -version 2>&1 | head -1 | grep -q '"25' || fail "java 25 is required, found: $(java -version 2>&1 | head -1)"

podman-compose pull
build_app

if [ -f "$ROOT/.gitignore" ]; then
  grep -q '^\.run/$' "$ROOT/.gitignore" || printf ".run/\n" >>"$ROOT/.gitignore"
  grep -q '^target/$' "$ROOT/.gitignore" || printf "target/\n" >>"$ROOT/.gitignore"
fi

log "setup done"
