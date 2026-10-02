#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require podman
require podman-compose
require python3
require curl
require lsof

python3 "$ROOT/app/dimensions.py"
compose pull i35-minio i35-rest i35-postgres i35-cassandra i35-trino
compose build i35-ui
log "setup done"
