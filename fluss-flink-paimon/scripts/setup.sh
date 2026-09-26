#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require podman
require podman-compose
require curl
require python3
require lsof
require java
require mvn

for image in "$FLUSS_IMAGE" "$ZOOKEEPER_IMAGE" "$JRE_IMAGE"; do
  log "pulling $image"
  podman pull -q "$image" >/dev/null || fail "could not pull $image"
done

log "building the java 25 app with maven and the $APP_IMAGE image"
build_app
mkdir -p "$RUN"
log "setup done"
