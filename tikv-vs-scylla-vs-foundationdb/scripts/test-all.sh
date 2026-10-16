#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require curl
require python3
require shasum
[ -f "$RESULTS" ] || fail "results.json missing, run ./scripts/start-all.sh first"
[ -f "$DATASET" ] || fail "data/dataset.csv missing, run ./scripts/setup.sh first"
port_up "$(service_port ui)" || fail "ui is down, run ./scripts/start-all.sh first"

API="$(service_url ui)/api"
RANGE=100

check() {
  if [ "$2" = "$3" ]; then
    log "PASS $1"
  else
    printf "FAIL %s\nexpected:\n%s\nactual:\n%s\n" "$1" "$2" "$3" >&2
    exit 1
  fi
}

key_at() {
  awk -F, -v row="$1" 'NR==row {print $1; exit}' "$DATASET"
}

value_at() {
  awk -F, -v row="$1" 'NR==row {print $2; exit}' "$DATASET"
}

rows_from() {
  awk -v row="$1" -v n="$RANGE" 'NR>=row && NR<row+n' "$DATASET"
}

api() {
  curl -sf --max-time 60 "$API/$1" || fail "GET /api/$1 failed"
}

sha="$(shasum -a 256 "$DATASET" | cut -d' ' -f1)"
log "shasum -a 256 data/dataset.csv: $sha ($ROWS rows)"
for store in $STORES; do
  check "$store live full ordered scan equals the dataset file byte for byte" "$sha $ROWS" "$(api "digest?store=$store")"
done

sample_rows="$(awk -v rows="$ROWS" 'BEGIN { for (row = 1; row <= rows; row += 19997) print row }')"
sample_count="$(printf "%s\n" "$sample_rows" | wc -l | tr -d ' ')"
expected_values="$(for row in $sample_rows; do value_at "$row"; done)"
for store in $STORES; do
  actual_values="$(for row in $sample_rows; do api "get?store=$store&key=$(key_at "$row")"; done)"
  check "$store $sample_count sampled point reads return the bytes awk reads from the file" "$expected_values" "$actual_values"
done

for store in $STORES; do
  check "$store answers 404 for a key that is not in the dataset" "404" "$(curl -s -o /dev/null -w '%{http_code}' "$API/get?store=$store&key=key-999999999999")"
done

for row in 1 951 $((ROWS - 49)); do
  expected_rows="$(rows_from "$row")"
  count="$(printf "%s\n" "$expected_rows" | wc -l | tr -d ' ')"
  for store in $STORES; do
    check "$store range scan from row $row returns the same $count ordered rows as awk" "$expected_rows" "$(api "scan?store=$store&start=$(key_at "$row")&n=$RANGE")"
  done
done

row=4243
key="$(key_at "$row")"
value="$(value_at "$row")"
check "foundationdb fdbcli get $key matches awk" "\`$key' is \`$value'" "$(fdbcli "get $key")"
check "scylladb cqlsh select $key matches awk" "$value" "$(cql "SELECT blobAsText(v) FROM s6.kv WHERE bucket = $(((row - 1) / 1000)) AND k = '$key'" | awk 'NR==4 {gsub(/ /, ""); print}')"

for store in scylladb foundationdb; do
  check "$store container has the same memory and cpu limit as tikv" "$(limits tikv)" "$(limits "$store")"
done

python3 -c '
import json, sys
data = json.load(open(sys.argv[1]))
sha, rows = sys.argv[2], int(sys.argv[3])
setup = data["setup"]
assert data["dataset_sha256"] == sha, "results.json was measured on a different dataset"
assert setup["rows"] == rows, "row count differs"
assert [s["name"] for s in data["stores"]] == sys.argv[4].split(), "stores differ"
expected_ops = {"point_read": setup["point_reads"], "range_scan": setup["range_scans"]}
for s in data["stores"]:
    assert s["full_scan_sha256"] == sha and s["full_scan_rows"] == rows, s["name"] + " was timed on different bytes"
    assert s["sample_keys_matching"] == setup["sample_keys"], s["name"] + " sampled keys differ"
    assert s["sample_ranges_matching"] == setup["sample_ranges"], s["name"] + " sampled ranges differ"
    assert s["load_seconds"] > 0
    ops = {o["operation"]: o for o in s["operations"]}
    assert set(ops) == set(expected_ops), s["name"] + " operations differ"
    for name, o in ops.items():
        assert o["ops"] == expected_ops[name], "%s %s ran %d operations, not %d" % (s["name"], name, o["ops"], expected_ops[name])
        assert o["errors"] == 0, "%s %s had %d errors" % (s["name"], name, o["errors"])
        assert 0 < o["p50_ms"] <= o["p95_ms"] <= o["p99_ms"] <= o["max_ms"], "%s %s percentiles out of order" % (s["name"], name)
        assert abs(o["throughput"] - o["ops"] / o["seconds"]) <= 0.01 * o["throughput"], "%s %s throughput is not ops / seconds" % (s["name"], name)
        print("%-13s %-11s %9.1f ops/s  p50 %7.3f ms  p95 %7.3f ms  p99 %7.3f ms  load %6.2f s" % (s["name"], name, o["throughput"], o["p50_ms"], o["p95_ms"], o["p99_ms"], s["load_seconds"]))
' "$RESULTS" "$sha" "$ROWS" "$STORES" || fail "results.json checks failed"
log "PASS results.json was measured on this dataset, same operation counts for every store, no errors, ordered percentiles, throughput equals ops / seconds"

curl -sf "$(service_url ui)/" | grep -q "TiKV vs ScyllaDB vs FoundationDB" || fail "ui page not served"
log "PASS ui page served"
log "all tests passed"
