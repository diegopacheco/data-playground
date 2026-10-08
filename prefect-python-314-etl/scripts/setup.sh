#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

log "setup started"

require podman-compose
podman-compose pull

require python3.14
if [ ! -x "$VENV/bin/python" ]; then
  python3.14 -m venv "$VENV"
fi
"$VENV/bin/pip" install -q -r "$ROOT/requirements.txt"
"$VENV/bin/python" --version
"$VENV/bin/python" -c "import prefect; print('prefect', prefect.__version__)"

log "setup done"
