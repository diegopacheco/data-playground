#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require podman
require podman-compose
require "$PYTHON_BIN"

if [ ! -x "$VENV/bin/python" ]; then
  log "creating virtualenv with $PYTHON_BIN"
  "$PYTHON_BIN" -m venv "$VENV" || fail "could not create virtualenv"
fi

log "installing python dependencies"
"$VENV/bin/pip" install -q -r "$ROOT/requirements.txt" || fail "pip install failed"

mkdir -p "$ROOT/jars"
if [ ! -f "$ROOT/jars/$ICEBERG_JAR" ]; then
  log "downloading $ICEBERG_JAR"
  "$VENV/bin/python" -c "import sys, urllib.request; urllib.request.urlretrieve(sys.argv[1], sys.argv[2])" "$ICEBERG_URL" "$ROOT/jars/$ICEBERG_JAR" || fail "iceberg jar download failed"
fi

if ! podman image exists "$SPARK_IMAGE"; then
  log "pulling $SPARK_IMAGE"
  podman pull "$SPARK_IMAGE" >/dev/null || fail "could not pull $SPARK_IMAGE"
fi

log "setup done"
