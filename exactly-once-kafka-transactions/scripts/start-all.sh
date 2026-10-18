#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require podman-compose
require curl
require java
[ -d "$ROOT/target/lib" ] || fail "app not built, run scripts/setup.sh first"
mkdir -p "$LOGS"

if ! port_up "$(service_port ui)"; then
  log "starting a fresh kafka broker"
  compose down >/dev/null 2>&1 || true
  compose up -d >"$LOGS/compose.log" 2>&1 || fail "podman-compose up failed, see .run/logs/compose.log"
  wait_until 60 kafka_ready || fail "kafka not ready, see: podman logs $KAFKA_CONTAINER"
  "$SCRIPTS/run-scenarios.sh" || fail "scenarios failed"
  log "starting ui"
  nohup "${JAVA[@]}" eos.UiServer >"$LOGS/ui.log" 2>&1 &
  echo $! >"$RUN/ui.pid"
  wait_until 60 curl -sf "$(service_url ui)/api/report" || fail "ui did not answer, see .run/logs/ui.log"
fi

"$SCRIPTS/status.sh" || fail "a service is down"

log "links"
printf "%-8s %s\n" kafka "$(service_url kafka)"
printf "%-8s %s\n" ui "$(service_url ui)"
printf "%-8s %s\n" api "$(service_url ui)/api/report"
printf "%-8s %s\n" api "$(service_url ui)/api/events"
