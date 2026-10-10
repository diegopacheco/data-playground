#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

log "tests started"

require python3
require awk
port_up "$(service_port ui)" || fail "ui is not running, run ./scripts/start-all.sh first"

"$SCRIPTS/pipeline.sh"

log "awk revenue per category before merge"
tail -n +2 "$ROOT/data/orders.csv" | awk -F, '{o[$4]++; r[$4]+=$5*$6} END {for (c in o) printf "  %-12s %3d %10.2f\n", c, o[c], r[c]}' | sort

log "awk revenue per category after merge"
awk -F, 'FNR==1{next} {row[$1]=$0} END {for (k in row) {split(row[k], f, ","); o[f[4]]++; r[f[4]]+=f[5]*f[6]} for (c in o) printf "  %-12s %3d %10.2f\n", c, o[c], r[c]}' "$ROOT/data/orders.csv" "$ROOT/data/updates.csv" | sort

python3 "$SCRIPTS/verify.py" "$ROOT" "$(service_url ui)/api" || fail "api results do not match the independent check"

log "tests passed"
