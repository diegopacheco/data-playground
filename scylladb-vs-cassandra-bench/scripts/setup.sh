#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require podman
require podman-compose
require mvn

log "using java at $JAVA_HOME"
"$JAVA_HOME/bin/java" -version 2>&1 | head -1

podman-compose pull >"$LOGS/pull.log" 2>&1 || fail "image pull failed, see $LOGS/pull.log"
mvn -q -B clean package -DskipTests || fail "maven build failed"

log "setup done"
