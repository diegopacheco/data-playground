#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require podman
require podman-compose
require curl
require python3
require lsof
mkdir -p "$ROOT/results" "$RUN/logs"

for image in $BASE_IMAGES; do
  log "pulling $image"
  podman pull -q "$image" >/dev/null || fail "could not pull $image"
done

log "building $APP_IMAGE (Nimble and Velox from source, the first build takes a long time), log in .run/logs/build.log"
status=0
podman build --memory "${BUILD_MEMORY:-7g}" --build-arg "JOBS=${JOBS:-3}" -t "$APP_IMAGE" -f "$ROOT/Containerfile" "$ROOT" >"$RUN/logs/build.log" 2>&1 || status=$?
[ "$status" = "0" ] || { tail -40 "$RUN/logs/build.log" >&2; fail "image build failed, see .run/logs/build.log"; }
podman run --rm -e LD_LIBRARY_PATH=/opt/nimble/lib "$APP_IMAGE" /opt/nimble/nimble_bench version >/dev/null || fail "nimble_bench does not run in $APP_IMAGE"
log "setup done"
