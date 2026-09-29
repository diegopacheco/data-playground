#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

log "setup started"

require podman-compose
require mvn
require python3.14

java25 mvn -q -B -DskipTests package || fail "maven build failed"

if [ ! -x "$VENV/bin/python" ]; then
  python3.14 -m venv "$VENV"
fi
"$VENV/bin/pip" install -q -r "$ROOT/client/requirements.txt" || fail "pip install failed"

podman-compose build || fail "image build failed"

log "setup done"
