#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require podman
require podman-compose
require curl
require lsof
require node

log "pulling $SQLD_IMAGE"
podman pull -q "$SQLD_IMAGE" >/dev/null || fail "could not pull $SQLD_IMAGE"
log "pulling $NODE_IMAGE"
podman pull -q "$NODE_IMAGE" >/dev/null || fail "could not pull $NODE_IMAGE"
log "building $APP_IMAGE with @libsql/client"
podman build -q -t "$APP_IMAGE" -f "$ROOT/Containerfile" "$ROOT" >/dev/null || fail "image build failed"
for c in t6-console $REPLICAS; do
  if [ "$(container_state "$c")" != "absent" ]; then
    podman rm -f "$c" >/dev/null || fail "could not remove the old $c container"
  fi
done
mkdir -p "$RUN/logs"
log "setup done"
