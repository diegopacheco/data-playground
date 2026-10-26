#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require curl
require python3
port_up "$(service_port ui)" || fail "ui is down, run scripts/start-all.sh first"

ORDERS="$ROOT/data/orders.csv"
INSERTS="$ROOT/data/dev_inserts.csv"
API="$(service_url ui)/api"
NESSIE="$(service_url nessie)/api/v2"

awk_initial() {
  awk -F, 'NR>1{c[$4]++;q[$4]+=$5;r[$4]+=$5*$6}END{for(k in c)printf "%s %d %d %.2f\n",k,c[k],q[k],r[k]}' "$ORDERS" | sort
}

python_dev() {
  python3 - "$ORDERS" "$INSERTS" <<'EOF'
import csv, sys
from decimal import Decimal, ROUND_HALF_UP
rows = list(csv.DictReader(open(sys.argv[1])))
out = []
for r in rows:
    if r["category"] == "toys":
        continue
    price = Decimal(r["price"])
    if r["category"] == "electronics":
        price = (price * Decimal("1.10")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    out.append((r["category"], int(r["quantity"]), price))
out += [(r["category"], int(r["quantity"]), Decimal(r["price"])) for r in csv.DictReader(open(sys.argv[2]))]
agg = {}
for cat, qty, price in out:
    c, q, rev = agg.get(cat, (0, 0, Decimal(0)))
    agg[cat] = (c + 1, q + qty, rev + qty * price)
for cat in sorted(agg):
    c, q, rev = agg[cat]
    print("%s %d %d %s" % (cat, c, q, rev))
EOF
}

api_revenue() {
  curl -sf "$API/revenue?ref=$1" | python3 -c 'import json,sys
from decimal import Decimal
for r in json.load(sys.stdin): print("%s %d %d %s" % (r["category"], r["orders"], r["quantity"], Decimal(r["revenue"]).quantize(Decimal("0.01"))))' | sort
}

ref_hash() {
  curl -sf "$NESSIE/trees/$1" | python3 -c 'import json,sys; print(json.load(sys.stdin)["reference"]["hash"])'
}

main_head_parent() {
  curl -sf "$NESSIE/trees/main/history?max-records=1" | python3 -c 'import json,sys; print(json.load(sys.stdin)["logEntries"][0]["parentCommitHash"])'
}

check() {
  if [ "$2" = "$3" ]; then
    log "PASS $1"
  else
    printf "FAIL %s\nexpected:\n%s\nactual:\n%s\n" "$1" "$2" "$3" >&2
    exit 1
  fi
}

expected_initial="$(awk_initial)"
expected_dev="$(python_dev)"

check "tag initial (main before branching) matches awk over orders.csv" "$expected_initial" "$(api_revenue initial)"
check "branch dev matches python replay of update, delete and insert" "$expected_dev" "$(api_revenue dev)"
check "branch main after merge equals the dev state" "$expected_dev" "$(api_revenue main)"
check "tag merged equals the dev state" "$expected_dev" "$(api_revenue merged)"
check "dev has no toys category" "" "$(api_revenue dev | awk '$1=="toys"')"
check "dev has the new garden category" "garden" "$(api_revenue dev | awk '$1=="garden"{print $1}')"
check "tag merged points at main head" "$(ref_hash main)" "$(ref_hash merged)"
check "merge commit sits right on top of tag initial, so main never moved while dev changed" "$(ref_hash initial)" "$(main_head_parent)"
check "commit log api returns the merge commit first" "merge dev into main" "$(curl -sf "$API/log?ref=main" | python3 -c 'import json,sys; print(json.load(sys.stdin)[0]["message"])')"

log "initial per category (category orders quantity revenue):"
printf "%s\n" "$expected_initial"
log "dev and merged main per category (category orders quantity revenue):"
printf "%s\n" "$expected_dev"
log "all tests passed"
