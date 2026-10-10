#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

PY="$ROOT/.venv/bin/python"
[ -x "$PY" ] || fail "virtualenv missing, run ./scripts/setup.sh first"
[ -f "$ROOT/results/results.json" ] || fail "results/results.json missing, run ./scripts/start-all.sh first"
[ -f "$ROOT/.lake/csv-none.csv" ] || fail ".lake/csv-none.csv missing, run RERUN=1 ./scripts/start-all.sh"

log "unit tests"
"$PY" -m unittest discover -s "$ROOT/tests" -v || fail "unit tests failed"

log "independent awk check of the csv aggregation against results.json"
awk -F, 'NR>1{gsub(/"/,"",$4); n[$4]++; q[$4]+=$5; r[$4]+=$5*$6} END{for(c in n) printf "%s %d %d %.2f\n", c, n[c], q[c], r[c]}' "$ROOT/.lake/csv-none.csv" | sort >"$RUN/awk.txt"
cat "$RUN/awk.txt"
"$PY" - "$ROOT/results/results.json" "$RUN/awk.txt" <<'PY' || fail "awk check failed"
import json, sys
report = json.load(open(sys.argv[1]))
awk = {c: (int(n), int(q), float(r)) for c, n, q, r in (l.split() for l in open(sys.argv[2]))}
ref = report["csv_reference"]
assert awk.keys() == ref.keys(), (awk.keys(), ref.keys())
for c, (n, q, r) in awk.items():
    assert (n, q) == (ref[c]["orders"], ref[c]["quantity"]), c
    assert abs(r - ref[c]["revenue"]) <= 0.01, c
assert sum(v[0] for v in awk.values()) == report["rows"]
assert report["all_ok"]
print("awk totals match results.json for", len(awk), "categories and", report["rows"], "rows")
PY

if port_up "$(service_port ui)"; then
  log "api check"
  curl -sf "$(service_url ui)/api/results" | "$PY" -c 'import json,sys; d=json.load(sys.stdin); assert d["all_ok"]; print("api all_ok", d["all_ok"], "variants", len(d["results"]))' || fail "api check failed"
  curl -sf "$(service_url ui)/" | grep -q "Parquet vs ORC vs Avro" || fail "ui page check failed"
fi

log "tests passed"
