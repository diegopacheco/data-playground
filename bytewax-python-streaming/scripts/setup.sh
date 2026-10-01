#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

log "setup started"

require podman
require podman-compose
require python3
require uv
podman-compose pull

if [ ! -x "$FLOW_PY" ]; then
  uv venv --python "$FLOW_PYTHON_VERSION" "$ROOT/.venv"
fi
uv pip install --python "$FLOW_PY" -r "$ROOT/dataflow/requirements.txt"

log "dataflow python $("$FLOW_PY" --version)"
log "ui python $(python3 --version)"
log "setup done"
