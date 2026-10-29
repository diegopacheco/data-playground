#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require curl
kestra_ready || fail "kestra is not running, run ./scripts/start-all.sh first"
api="$(kestra_api)"

code="$(kcurl -o "$LOGS/nsfile.json" -w '%{http_code}' -X POST "$api/namespaces/$NAMESPACE/files?path=/data/orders.csv" -F "fileContent=@$ROOT/data/orders.csv")"
case "$code" in
  2*) log "uploaded namespace file data/orders.csv to $NAMESPACE" ;;
  *) fail "namespace file upload returned $code: $(cat "$LOGS/nsfile.json")" ;;
esac

for flow in "$PIPELINE_FLOW" "$QUALITY_FLOW"; do
  file="$ROOT/flows/$flow.yml"
  code="$(kcurl -o "$LOGS/deploy-$flow.json" -w '%{http_code}' -X PUT -H 'Content-Type: application/x-yaml' --data-binary "@$file" "$api/flows/$NAMESPACE/$flow")"
  if [ "$code" = "404" ]; then
    code="$(kcurl -o "$LOGS/deploy-$flow.json" -w '%{http_code}' -X POST -H 'Content-Type: application/x-yaml' --data-binary "@$file" "$api/flows")"
  fi
  case "$code" in
    2*) log "deployed flow $NAMESPACE.$flow revision $(json_field revision <"$LOGS/deploy-$flow.json")" ;;
    *) fail "deploy of $flow returned $code: $(cat "$LOGS/deploy-$flow.json")" ;;
  esac
done
