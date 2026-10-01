#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require podman
require podman-compose
require lsof
require curl
require awk
require shasum

[ -f "$ORDERS_CSV" ] || fail "missing $ORDERS_CSV"
mkdir -p "$ROOT/lake" "$RESULTS_DIR" "$RUN/m2" "$RUN/xtable-target" "$ROOT/xtable/dist"

log "pulling runtime images"
for image in $MAVEN_IMAGE $JRE17_IMAGE $JDK25_IMAGE; do
  podman image exists "$image" || podman pull "$image" >>"$LOGS/setup.log" 2>&1 || fail "cannot pull $image"
done

if [ -f "$XTABLE_JAR" ]; then
  log "xtable utilities jar already built"
else
  log "building apache xtable $XTABLE_TAG utilities bundle from source inside a container"
  podman build --build-arg "XTABLE_TAG=$XTABLE_TAG" -t "$XTABLE_BUILDER" "$ROOT/xtable" >>"$LOGS/setup.log" 2>&1 || fail "xtable builder image failed, see $LOGS/setup.log"
  podman run --rm --name i8-xtable-build -v "$RUN/m2:/root/.m2" -v "$RUN/xtable-target:/src/xtable-utilities/target" -v "$ROOT/xtable/dist:/out" "$XTABLE_BUILDER" >>"$LOGS/setup.log" 2>&1 || fail "xtable build failed, see $LOGS/setup.log"
fi

if [ -f "$ROOT/spark/target/lake-jobs.jar" ]; then
  log "spark jobs jar already built"
else
  log "building spark jobs jar inside a maven container"
  podman run --rm --name i8-spark-build -v "$ROOT/spark:/build" -v "$RUN/m2:/root/.m2" -w /build "$MAVEN_IMAGE" mvn -B -q package >>"$LOGS/setup.log" 2>&1 || fail "spark jobs build failed, see $LOGS/setup.log"
fi

log "setup done"
