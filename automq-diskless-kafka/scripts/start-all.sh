#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require podman
require podman-compose
require curl
podman image exists "$APP_IMAGE" || fail "image $APP_IMAGE missing, run scripts/setup.sh first"
data_ready || fail "data/orders.jsonl missing, run scripts/setup.sh first"
mkdir -p "$ROOT/results" "$RUN/logs"

log "starting minio"
compose up -d r9-minio >/dev/null 2>&1 || fail "podman-compose up r9-minio failed"
wait_until 60 curl -sf "$(service_url minio)/minio/health/live" || fail "minio not ready, see: podman logs r9-minio"
log "minio up on $(service_url minio)"

log "starting ui (creates the r9-automq-data and r9-automq-ops buckets)"
compose up -d r9-app >/dev/null 2>&1 || fail "podman-compose up r9-app failed"
wait_until 60 curl -sf "$(service_url ui)/api/health" || fail "ui did not answer, see: podman logs r9-app"
log "ui up on $(service_url ui)"

log "starting automq controller (node 0) and stateless broker (node 1)"
compose up -d r9-controller r9-broker >/dev/null 2>&1 || fail "podman-compose up automq failed"
wait_until 60 node_ready r9-controller 0 || fail "controller not ready, see: podman logs r9-controller"
wait_until 60 node_ready r9-broker 1 || fail "broker not ready, see: podman logs r9-broker"
wait_until 60 brokers_registered || fail "brokers did not register, see: podman logs r9-controller"
log "automq up on $(service_url controller) and $(service_url broker)"

if [ -f "$ROOT/results/proof.json" ]; then
  log "results/proof.json exists, skipping the proof run (run scripts/proof.sh to rerun)"
else
  "$SCRIPTS/proof.sh"
fi

"$SCRIPTS/status.sh"

log "links"
for name in $(service_names); do
  printf "%-11s %s\n" "$name" "$(service_url "$name")"
done
printf "%-11s %s\n" api "$(service_url ui)/api/proof"
