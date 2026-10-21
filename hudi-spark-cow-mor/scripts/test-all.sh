#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

log "tests started"

require sbt
require python3
require curl
port_up "$(service_port ui)" || fail "ui is not running, run ./scripts/start-all.sh first"

log "running hudi benchmark, log in $LOGS/bench.log"
sbt -batch bench/run >"$LOGS/bench.log" 2>&1 || fail "benchmark failed, see $LOGS/bench.log"
grep -E '^(orders|cow|mor|compaction)' "$LOGS/bench.log" || true

RESULTS="$RESULTS_DIR/results.json"
[ -f "$RESULTS" ] || fail "missing $RESULTS"

expected="$(tail -n +2 "$ORDERS_CSV" | awk -F, '{
  cents = int($6 * 100 + 0.5)
  for (c = 0; c < 2500; c++) {
    oid = c * 10000 + $1
    q = $5 + c % 3
    r = oid % 10
    if (r < 3) q += r + 1
    o[$4]++; qs[$4] += q; rv[$4] += q * cents
  }
} END { for (k in o) printf "%s %d %d %d.%02d\n", k, o[k], qs[k], int(rv[k] / 100), rv[k] % 100 }' | sort)"

log "expected from awk recomputation"
log "$expected"

for name in cow_snapshot mor_snapshot_before_compaction mor_snapshot_after_compaction mor_read_optimized_after_compaction; do
  actual="$(python3 -c 'import json,sys
for r in json.load(open(sys.argv[1]))["aggregates"][sys.argv[2]]: print(r["category"], r["orders"], r["quantity"], r["revenue"])' "$RESULTS" "$name" | sort)"
  [ "$expected" = "$actual" ] || fail "$name does not match awk recomputation: $actual"
  log "$name matches awk recomputation"
done

python3 -c 'import json,sys
d = json.load(open(sys.argv[1]))
bad = [k for k, v in d["checks"].items() if v is not True]
assert not bad, "failed checks: %s" % bad
assert d["rows"] == 500000, d["rows"]
assert d["batchUpdates"] == [50000, 50000, 50000], d["batchUpdates"]
for t in ("cow", "mor"):
    assert all(s["snapshotRows"] == 500000 for s in d["tables"][t]), t
mor = {s["step"]: s for s in d["tables"]["mor"]}
assert mor["upsert 3"]["storage"]["logFiles"] > 0, "mor upserts wrote no log files"
assert mor["compaction"]["storage"]["baseFiles"] > mor["upsert 3"]["storage"]["baseFiles"], "compaction wrote no base files"
print("checks:", ", ".join(d["checks"]))' "$RESULTS" || fail "results.json checks failed"

api="$(curl -sf "$(service_url ui)/api/results")" || fail "api did not answer"
[ "$api" = "$(cat "$RESULTS")" ] || fail "api payload differs from results.json"
log "api serves the same results.json"

log "tests passed"
