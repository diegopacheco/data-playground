#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require podman
require podman-compose
require python3.14

if [ ! -x "$PY" ]; then
  log "creating python 3.14 venv"
  python3.14 -m venv "$ROOT/.venv"
fi
log "installing python dependencies"
"$PY" -m pip install -q -r "$ROOT/requirements.txt" || fail "pip install failed"
log "downloading embedding model into .models"
(cd "$ROOT/app" && "$PY" -c "from embed import model; model()" 2>/dev/null) || fail "model download failed"
log "pulling $IMAGE"
podman pull -q "$IMAGE" >/dev/null || fail "could not pull $IMAGE"
log "setup done"
