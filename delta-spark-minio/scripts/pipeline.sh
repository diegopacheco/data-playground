#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

port_up "$(service_port minio)" || fail "minio is not running, run ./scripts/start-all.sh first"

require sbt
sbt -batch job/run || fail "delta job failed"
log "delta job wrote reports into output/"
