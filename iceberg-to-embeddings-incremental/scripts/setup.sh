#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require podman
require podman-compose
require python3.14
require lsof
require curl

if [ ! -x "$PY" ]; then
  log "creating python 3.14 venv"
  python3.14 -m venv "$ROOT/.venv" || fail "venv creation failed"
fi
log "installing python requirements"
"$PY" -m pip install -q -r "$ROOT/requirements.txt" || fail "pip install failed"
log "downloading embedding model into .models"
"$PY" -c 'import sys
sys.path.insert(0, sys.argv[1])
from embed import model
model()' "$ROOT/app" 2>/dev/null || fail "model download failed"
log "pulling images"
for image in "$MINIO_IMAGE" "$REST_IMAGE" "$POSTGRES_IMAGE"; do
  podman pull -q "$image" >/dev/null || fail "could not pull $image"
done
mkdir -p "$RUN/logs"
log "setup done"
