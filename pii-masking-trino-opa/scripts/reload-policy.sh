#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require curl
POLICY="${1:-$ROOT/opa/policy}"
OPA="$(service_url opa)"
opa_ready >/dev/null || fail "opa is down, run scripts/start-all.sh first"

for file in "$POLICY"/*.rego; do
  curl -sf -X PUT -H "Content-Type: text/plain" --data-binary "@$file" "$OPA/v1/policies/s5/policy/$(basename "$file")" >/dev/null \
    || fail "opa rejected $(basename "$file")"
done
curl -sf -X PUT -H "Content-Type: application/json" --data-binary "@$POLICY/pii/data.json" "$OPA/v1/data/pii" >/dev/null \
  || fail "opa rejected pii/data.json"
log "opa reloaded rego and data, trino started at $(trino_started) and was not restarted"
