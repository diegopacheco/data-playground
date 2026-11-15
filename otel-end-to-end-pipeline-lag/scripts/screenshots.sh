#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

PLAYWRIGHT="playwright@1.64.1"
OUT="$ROOT/printscreens"
require bunx
for name in grafana jaeger prometheus; do
  port_up "$(service_port "$name")" || fail "$name is DOWN, run scripts/start-all.sh first"
done

trace_id="$(k exec deploy/postgres -- psql -U pipeline -d pipeline -At -c \
  "SELECT trace_id FROM sink_orders WHERE run_id LIKE 'trace-%' ORDER BY sink_time DESC LIMIT 1")"
[ -n "$trace_id" ] || fail "no traced message in sink_orders, run scripts/test-all.sh first"

mkdir -p "$OUT"
bunx "$PLAYWRIGHT" install chromium >/dev/null || fail "playwright browser install failed"
shoot() {
  bunx "$PLAYWRIGHT" screenshot --browser chromium --viewport-size "1600,1000" --wait-for-timeout 10000 "$1" "$OUT/$2" >/dev/null \
    || fail "screenshot $2 failed"
}
shoot "$(service_base grafana)/d/pipeline-lag?orgId=1&from=now-20m&to=now&kiosk" 1-grafana-dashboard.png
shoot "$(service_base jaeger)/trace/$trace_id" 2-jaeger-trace.png
shoot "$(service_base prometheus)/alerts" 3-prometheus-alerts.png
(cd "$ROOT/e2e" && uv run -q python -m harness.png "$OUT"/*.png) || fail "png metadata strip failed"
log "screenshots in printscreens/ (trace $trace_id)"
