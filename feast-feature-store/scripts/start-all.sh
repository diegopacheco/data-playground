#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require podman
require podman-compose
require curl
podman image exists "$APP_IMAGE" || fail "image $APP_IMAGE missing, run scripts/setup.sh first"
mkdir -p "$ROOT/data" "$RUN/logs"

log "starting redis"
compose up -d r16-redis >/dev/null 2>&1 || fail "podman-compose up r16-redis failed"
wait_until 60 redis_ready || fail "redis not ready, see: podman logs r16-redis"
log "redis up on $(service_url redis)"

log "starting app: generate parquet, feast apply, materialize_incremental into redis, historical retrieval"
compose up -d r16-app >/dev/null 2>&1 || fail "podman-compose up r16-app failed"
wait_until 60 http_ok "$(service_url ui)/api/state" || fail "app did not answer, see: podman logs r16-app"
log "ui up on $(service_url ui)"

log "starting feast feature server"
compose up -d r16-feature-server >/dev/null 2>&1 || fail "podman-compose up r16-feature-server failed"
wait_until 60 http_ok "$(service_url featureserver)/health" || fail "feature server did not answer, see: podman logs r16-feature-server"
log "feature server up on $(service_url featureserver)"

"$SCRIPTS/status.sh"

log "links"
printf "%-14s %s\n" ui "$(service_url ui)"
printf "%-14s %s\n" api "$(service_url ui)/api/state"
printf "%-14s %s\n" featureserver "$(service_url featureserver)/get-online-features"
printf "%-14s %s\n" redis "$(service_url redis)"
