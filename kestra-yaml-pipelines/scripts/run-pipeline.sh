#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require curl
require python3
kestra_ready || fail "kestra is not running, run ./scripts/start-all.sh first"
api="$(kestra_api)"

expect_success() {
  local state
  state="$(wait_final_state "$1")"
  [ "$state" = "SUCCESS" ] || fail "execution $1 ended $state, see $(service_url kestra)/ui/main/executions?namespace=$NAMESPACE"
  log "execution $1 SUCCESS"
}

quality_after() {
  kcurl "$api/executions/search?namespace=$NAMESPACE&flowId=$QUALITY_FLOW&size=20" | python3 -c '
import json, sys
for e in json.load(sys.stdin)["results"]:
    t = e.get("trigger") or {}
    if (t.get("variables") or {}).get("executionId") == sys.argv[1]:
        print(e["id"])
        break
' "$1"
}

pipeline_id="$(kcurl -X POST "$api/executions/$NAMESPACE/$PIPELINE_FLOW" | json_field id)"
[ -n "$pipeline_id" ] || fail "could not start $PIPELINE_FLOW"
log "started $PIPELINE_FLOW execution $pipeline_id"
expect_success "$pipeline_id"

tries=60
quality_id=""
while [ "$tries" -gt 0 ] && [ -z "$quality_id" ]; do
  quality_id="$(quality_after "$pipeline_id")"
  [ -n "$quality_id" ] || sleep 1
  tries=$((tries - 1))
done
[ -n "$quality_id" ] || fail "flow trigger did not start $QUALITY_FLOW after $pipeline_id"
log "flow trigger started $QUALITY_FLOW execution $quality_id"
expect_success "$quality_id"
printf "%s %s\n" "$pipeline_id" "$quality_id" >"$RUN/last-run"
