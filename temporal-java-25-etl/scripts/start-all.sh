#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

log "starting"

require podman-compose
require java
podman-compose up -d

wait_port_up "$(service_port postgres)" 60 || fail "postgres did not open port $(service_port postgres)"
wait_until 60 pg_ready || fail "postgres not ready, see podman logs $POSTGRES_CONTAINER"
log "postgres up on $(service_url postgres)"

wait_port_up "$(service_port temporal)" 60 || fail "temporal did not open port $(service_port temporal)"
wait_until 60 temporal_ready || fail "temporal not ready, see podman logs $TEMPORAL_CONTAINER"
wait_port_up "$(service_port temporal-ui)" 60 || fail "temporal web ui did not open port $(service_port temporal-ui)"
log "temporal up on $(service_url temporal)"

[ -d "$ROOT/target/lib" ] || build_app
start_worker

start_bg ui java -Xmx256m --sun-misc-unsafe-memory-access=allow -cp "$CLASSPATH_APP" "$PKG.UiServer"
wait_port_up "$(service_port ui)" 60 || fail "ui did not open port $(service_port ui), see $LOGS/ui.log"
log "ui up on $(service_url ui)"

if podman exec "$TEMPORAL_CONTAINER" temporal workflow count --address 127.0.0.1:7233 --query "WorkflowType='EtlWorkflow'" | grep -q 'Total: 0'; then
  "$SCRIPTS/etl.sh" 2 5
fi

"$SCRIPTS/status.sh"

log "links"
for name in $(service_names); do
  printf "%-12s %s\n" "$name" "$(service_url "$name")"
done
printf "%-12s %s\n" "api" "$(service_url ui)/api/revenue"
printf "%-12s %s\n" "workflows" "$(service_url ui)/api/workflows"
