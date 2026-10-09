#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require curl
require python3
port_up "$(service_port ui)" || fail "ui is down, run scripts/start-all.sh first"

ORDERS="$ROOT/data/orders.csv"
UPDATES="$ROOT/data/updates.csv"
API="$(service_url ui)/api"

awk_initial() {
  awk -F, 'NR>1 && NR<=151{c[$4]++;q[$4]+=$5;r[$4]+=$5*$6}END{for(k in c)printf "%s %d %d %.2f\n",k,c[k],q[k],r[k]}' "$ORDERS" | sort
}

awk_all() {
  awk -F, 'NR>1{c[$4]++;q[$4]+=$5;r[$4]+=$5*$6}END{for(k in c)printf "%s %d %d %.2f\n",k,c[k],q[k],r[k]}' "$ORDERS" | sort
}

awk_merged() {
  awk -F, 'FNR==1{next} FILENAME==ARGV[1]{u[$1]=$0;next} {seen[$1]=1; if($1 in u){split(u[$1],n,",");$6=n[6]} c[$4]++;q[$4]+=$5;r[$4]+=$5*$6}
    END{for(id in u) if(!(id in seen)){split(u[id],n,",");c[n[4]]++;q[n[4]]+=n[5];r[n[4]]+=n[5]*n[6]} for(k in c)printf "%s %d %d %.2f\n",k,c[k],q[k],r[k]}' "$UPDATES" "$ORDERS" | sort
}

format_categories() {
  python3 -c 'import json,sys
for r in json.load(sys.stdin)["categories"]: print("%s %d %d %.2f" % (r["category"], r["total_orders"], r["total_quantity"], r["total_revenue"]))' | sort
}

versions="$(curl -sf "$API/versions")" || fail "GET /api/versions failed"

api_version() {
  printf "%s" "$versions" | python3 -c 'import json,sys
v=[x for x in json.load(sys.stdin) if x["version"]==int(sys.argv[1])][0]
print(json.dumps(v))' "$1" | format_categories
}

check() {
  if [ "$2" = "$3" ]; then
    log "PASS $1"
  else
    printf "FAIL %s\nexpected:\n%s\nactual:\n%s\n" "$1" "$2" "$3" >&2
    exit 1
  fi
}

operations="$(printf "%s" "$versions" | python3 -c 'import json,sys
print(" ".join(v["operation"] for v in json.load(sys.stdin)))')"
log "operations: $operations"
case "$operations" in
  "WRITE WRITE MERGE OPTIMIZE"*) log "PASS commit log is write, append, merge, optimize" ;;
  *) fail "unexpected commit log: $operations" ;;
esac

last_files="$(printf "%s" "$versions" | python3 -c 'import json,sys
print([v for v in json.load(sys.stdin) if v["operation"]=="OPTIMIZE"][-1]["files"])')"
check "optimize compacted to one file per category partition" "6" "$last_files"

check "v0 initial 150 orders match awk" "$(awk_initial)" "$(api_version 0)"
check "v1 append of all 200 orders matches awk" "$(awk_all)" "$(api_version 1)"
check "v2 merge upsert matches awk join of updates.csv" "$(awk_merged)" "$(api_version 2)"
check "v3 optimize keeps the data of v2" "$(awk_merged)" "$(api_version 3)"
check "latest version matches merged awk" "$(awk_merged)" "$(curl -sf "$API/revenue" | format_categories)"
check "time travel /api/revenue?version=0 matches awk" "$(awk_initial)" "$(curl -sf "$API/revenue?version=0" | format_categories)"

log "merged per category (category orders quantity revenue):"
awk_merged
log "all tests passed"
