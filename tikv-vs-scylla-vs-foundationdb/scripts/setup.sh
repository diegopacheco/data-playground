#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require podman
require podman-compose
require curl
require awk
require shasum
require python3
require lsof

if [ ! -f "$DATASET" ] || [ "$(wc -l <"$DATASET" | tr -d ' ')" != "$ROWS" ]; then
  log "generating $ROWS rows into data/dataset.csv with awk"
  mkdir -p "$ROOT/data"
  awk -v rows="$ROWS" 'BEGIN {
      x = 42
      for (i = 0; i < rows; i++) {
        v = ""
        for (j = 0; j < 10; j++) { x = (x * 16807) % 2147483647; v = v sprintf("%010d", x) }
        printf "key-%012d,%s\n", i, v
      }
    }' >"$DATASET.tmp" || fail "dataset generation failed"
  mv "$DATASET.tmp" "$DATASET"
fi
log "dataset sha256 $(shasum -a 256 "$DATASET" | cut -d' ' -f1)"

log "pulling images"
for image in $(grep -h '^FROM docker.io' "$ROOT"/Containerfile* | awk '{print $2}' | sort -u) $(awk '$1=="image:" && $2 ~ /^docker.io/ {print $2}' "$ROOT/podman-compose.yml"); do
  podman pull -q "$image" >>"$LOGS/pull.log" 2>&1 || fail "pull of $image failed, see .run/logs/pull.log"
done

log "building $TIKV_IMAGE (official tikv-server with debug symbols stripped)"
podman build -q -t "$TIKV_IMAGE" -f "$ROOT/Containerfile.tikv" "$ROOT" >"$LOGS/build-tikv.log" 2>&1 || fail "tikv image build failed, see .run/logs/build-tikv.log"

log "building $IMAGE (maven build and benchmark client with libfdb_c)"
podman build -q -t "$IMAGE" -f "$ROOT/Containerfile" "$ROOT" >"$LOGS/build.log" 2>&1 || fail "image build failed, see .run/logs/build.log"

log "setup done"
