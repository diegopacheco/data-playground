#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require podman
require podman-compose
require java
require mvn
require jq
require lsof
require curl

log "pulling images"
podman pull -q docker.io/apache/kafka:4.3.1 >/dev/null || fail "kafka pull failed"
log "building java app"
mvn -q -B -f "$ROOT/pom.xml" clean package -DskipTests || fail "maven build failed"
mkdir -p "$LOGS"
log "setup done"
