#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require podman
require podman-compose
require python3.14
require curl
require lsof

if [ ! -x "$PY" ]; then
  log "creating python 3.14 venv"
  python3.14 -m venv "$ROOT/.venv" || fail "could not create venv"
fi

"$PY" "$ROOT/app/generate.py" || fail "could not generate data"

for image in docker.io/library/postgres:18.6 "$OPA_IMAGE" docker.io/trinodb/trino:483; do
  log "pulling $image"
  podman pull -q "$image" >/dev/null || fail "could not pull $image"
done
log "setup done"
