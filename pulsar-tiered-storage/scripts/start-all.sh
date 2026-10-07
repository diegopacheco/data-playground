#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require podman
require podman-compose
require curl
require python3
podman image exists "$APP_IMAGE" || fail "image $APP_IMAGE missing, run scripts/setup.sh first"
podman image exists "$BROKER_IMAGE" || fail "image $BROKER_IMAGE missing, run scripts/setup.sh first"
[ -f "$ROOT/data/readings.csv" ] || fail "data/readings.csv missing, run scripts/setup.sh first"

log "starting zookeeper and minio"
compose up -d r7-zookeeper r7-minio >/dev/null 2>&1 || fail "podman-compose up r7-zookeeper r7-minio failed"
wait_until 60 zookeeper_ready || fail "zookeeper not ready, see: podman logs r7-zookeeper"

if ! exited_ok r7-pulsar-init; then
  log "writing the r7-cluster metadata into zookeeper"
  compose up -d r7-pulsar-init >/dev/null 2>&1 || fail "podman-compose up r7-pulsar-init failed"
  wait_until 60 exited_ok r7-pulsar-init || fail "cluster metadata init failed, see: podman logs r7-pulsar-init"
fi
if ! exited_ok r7-minio-init; then
  log "creating the pulsar-offload bucket"
  compose up -d r7-minio-init >/dev/null 2>&1 || fail "podman-compose up r7-minio-init failed"
  wait_until 60 exited_ok r7-minio-init || fail "bucket creation failed, see: podman logs r7-minio-init"
fi

log "starting the bookie (storage) and the broker (compute)"
compose up -d r7-bookie >/dev/null 2>&1 || fail "podman-compose up r7-bookie failed"
wait_until 60 bookie_ready || fail "bookie not ready, see: podman logs r7-bookie"
compose up -d r7-broker >/dev/null 2>&1 || fail "podman-compose up r7-broker failed"
wait_until 60 broker_ready || fail "broker not healthy, see: podman logs r7-broker"

log "starting the app"
compose up -d r7-app >/dev/null 2>&1 || fail "podman-compose up r7-app failed"
wait_until 60 api cluster || fail "app did not answer, see: podman logs r7-app"

if [ "$(api topic | json_field exists)" = "True" ]; then
  log "topic already holds data, skipping publish"
else
  log "publishing data/readings.csv"
  api_post publish >/dev/null || fail "publish failed, see: podman logs r7-app"
fi

"$SCRIPTS/status.sh"

log "links"
printf "%-10s %s\n" ui "$(service_url ui)"
printf "%-10s %s\n" broker "$(service_url broker)/brokers/r7-cluster"
printf "%-10s %s\n" bookie "$(service_url bookie)/ledger/list/"
printf "%-10s %s\n" minio "$(service_url minio)/pulsar-offload?list-type=2"
printf "%-10s %s\n" console "$(service_url console)"
printf "%-10s %s\n" topic "$(service_url ui)/api/topic"
