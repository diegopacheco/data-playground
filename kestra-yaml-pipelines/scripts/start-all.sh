#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require podman-compose
log "starting"
podman-compose up -d >"$LOGS/compose-up.log" 2>&1 || fail "podman-compose up failed, see $LOGS/compose-up.log"

wait_cmd 60 postgres_ready || fail "postgres did not become ready"
log "postgres up on $(service_url postgres)"

wait_cmd 60 kestra_ready || wait_cmd 60 kestra_ready || fail "kestra did not become ready, see podman logs i40-kestra"
log "kestra up on $(service_url kestra)"

"$SCRIPTS/deploy-flows.sh"

wait_cmd 30 http_ok "$(service_url ui)/" || fail "ui did not become ready, see podman logs i40-ui"
log "ui up on $(service_url ui)"

"$SCRIPTS/status.sh" || true

log "links"
for name in $(service_names); do
  printf "%-10s %s\n" "$name" "$(service_url "$name")"
done
printf "%-10s %s\n" "kestra-ui" "$(service_url kestra)/ui/main/flows?namespace=$NAMESPACE"
printf "%-10s %s\n" "kestra-api" "$(kestra_api)"
printf "%-10s %s\n" "api" "$(service_url ui)/api/revenue"
log "kestra login $(printf "%s" "$KESTRA_AUTH" | cut -d: -f1) / $(printf "%s" "$KESTRA_AUTH" | cut -d: -f2)"
