#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require curl
port_up "$(service_port ui)" || fail "app is down, run scripts/start-all.sh first"

log "running dlt pipeline: postgres orders + rest customers into duckdb"
api_post /api/run | python3 -c 'import json,sys; r=json.load(sys.stdin); print("run #%d load %s in %s ms, rows %s, new columns %s" % (r["run"], ",".join(r["load_ids"]), r["duration_ms"], r["row_counts"], r["new_columns"]))' || fail "pipeline run failed, see: podman logs r4-app"
