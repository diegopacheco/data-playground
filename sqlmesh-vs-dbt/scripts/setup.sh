#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

log "setup started"
require python3.14
require podman
require podman-compose

if [ ! -x "$VENV/bin/python" ]; then
  python3.14 -m venv "$VENV"
fi
"$VENV/bin/pip" install -q --upgrade pip
"$VENV/bin/pip" install -q -r "$ROOT/requirements.txt"
"$VENV/bin/pip" check >/dev/null || fail "pip check found broken requirements"

podman image exists docker.io/library/python:3.14.7-slim || podman pull docker.io/library/python:3.14.7-slim

if [ ! -f "$ROOT/comparison.json" ]; then
  bash "$ROOT/bench/run.sh" || fail "benchmark pipeline failed, see $LOGS"
fi

log "setup done"
