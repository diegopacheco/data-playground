#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require podman
require podman-compose
require java
require mvn

java -version 2>&1 | grep -q 'version "25' || fail "java 25 is required"

log "pulling images"
podman-compose pull >/dev/null || fail "podman-compose pull failed"

log "building app"
build_app

mkdir -p "$WAREHOUSE"
log "setup done"
