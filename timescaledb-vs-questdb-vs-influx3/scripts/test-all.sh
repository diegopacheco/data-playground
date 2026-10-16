#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require curl
port_up "$(service_port ui)" || fail "ui is down, run scripts/start-all.sh first"

READINGS="$ROOT/data/readings.csv"
API="$(service_url ui)/api"
OUT="$RUN/test"
mkdir -p "$OUT"

check() {
  if [ "$2" = "$3" ]; then
    log "PASS $1"
  else
    printf "FAIL %s\nexpected:\n%s\nactual:\n%s\n" "$1" "$2" "$3" >&2
    exit 1
  fi
}

result() {
  "$PY" -c 'import json,sys
v=json.load(open(sys.argv[1]))
for k in sys.argv[2].split("."): v=v[k]
print(v)' "$RUN/results.json" "$1"
}

log "computing the 1-hour downsample with awk from data/readings.csv"
awk -F, 'NR>1 {
    k = $1 " " int($2 / 3600) * 3600
    n[k]++; s[k] += $3
    if (!(k in lo) || $3 < lo[k]) lo[k] = $3
    if (!(k in hi) || $3 > hi[k]) hi[k] = $3
    d[$1] = 1
  } END {
    for (k in n) printf "%s %.6f %.6f %.6f\n", k, s[k] / n[k], lo[k], hi[k]
    for (k in d) devices++
    printf "%d %d\n", NR - 1, devices > "/dev/stderr"
  }' "$READINGS" 2>"$OUT/shape.txt" | LC_ALL=C sort >"$OUT/expected.txt"

check "csv holds the readings and devices the pipeline reports" "$(result dataset.points) $(result dataset.devices)" "$(cat "$OUT/shape.txt")"
check "awk yields one bucket per device per hour" "$(( $(result dataset.devices) * $(result dataset.days) * 24 ))" "$(wc -l <"$OUT/expected.txt" | tr -d ' ')"

for engine in timescaledb questdb influx3; do
  for source in raw rollup; do
    curl -sf "$API/hourly?engine=$engine&source=$source" | LC_ALL=C sort >"$OUT/$engine-$source.txt" || fail "GET /api/hourly $engine $source failed"
    check "$engine 1-hour downsample from $source equals awk" "0" "$(diff "$OUT/expected.txt" "$OUT/$engine-$source.txt" | grep -c '^[<>]' || true)"
  done
done

check "three engines stored the same number of readings" "$(result dataset.points) $(result dataset.points) $(result dataset.points)" \
  "$(psql_exec -Atc 'SELECT count(*) FROM readings') $(curl -sf -G "$(service_url questdb)/exec" --data-urlencode 'query=SELECT count() FROM readings' | "$PY" -c 'import json,sys; print(json.load(sys.stdin)["dataset"][0][0])') $("$PY" -c 'import sys
sys.path.insert(0, sys.argv[1])
import influx
print(influx.count())' "$ROOT/app")"

check "timescaledb readings_1h is a continuous aggregate" "1" "$(psql_exec -Atc "SELECT count(*) FROM timescaledb_information.continuous_aggregates WHERE view_name = 'readings_1h'")"
check "timescaledb compressed every chunk into the columnstore" "$(result dataset.days)" "$(psql_exec -Atc "SELECT count(*) FROM timescaledb_information.chunks WHERE hypertable_name = 'readings' AND is_compressed")"
smaller="$(( $(result engines.timescaledb.disk_columnstore.data) < $(result engines.timescaledb.disk.data) ))"
check "timescaledb columnstore is smaller than rowstore" "1" "$smaller"
check "questdb readings_1h is a valid materialized view" "valid" "$(curl -sf -G "$(service_url questdb)/exec" --data-urlencode "query=SELECT view_status FROM materialized_views() WHERE view_name = 'readings_1h'" | "$PY" -c 'import json,sys; print(json.load(sys.stdin)["dataset"][0][0])')"

influx_sql() {
  curl -s -o "$OUT/influx.out" -w '%{http_code}' -X POST "$(service_url influx3)/api/v3/query_sql" -H 'Content-Type: application/json' -d "{\"db\":\"s7\",\"q\":\"$1\",\"format\":\"csv\"}" || true
}

code="$(influx_sql "SELECT device, date_bin(INTERVAL '1 hour', time) AS bucket, avg(temperature) FROM readings GROUP BY 1, 2")"
check "influxdb 3 core rejects the 4-day downsample as one statement" "500 1" "$code $(grep -c 'exceeding the file limit' "$OUT/influx.out" || true)"
code="$(influx_sql "SELECT trigger_name, plugin_filename FROM system.processing_engine_triggers")"
check "influxdb 3 core rollup is a processing engine trigger" "200 rollup,rollup.py" "$code $(tail -1 "$OUT/influx.out")"

log "measured (engine ingest_rows_per_s table_bytes 1h_ms 1m_ms last_ms scan_ms rollup_ms):"
"$PY" -c 'import json,sys
r=json.load(open(sys.argv[1]))["engines"]
def line(name, e, q, disk):
    print(name, e["ingest"]["rows_per_s"], disk["data"], *[q[k]["median_ms"] for k in ("downsample_1h","downsample_1m","last_value","range_scan")], e["queries"]["rollup_1h"]["median_ms"])
t=r["timescaledb"]
line("timescaledb-rowstore", t, t["queries_rowstore"], t["disk"])
line("timescaledb-columnstore", t, t["queries"], t["disk_columnstore"])
line("questdb", r["questdb"], r["questdb"]["queries"], r["questdb"]["disk"])
line("influx3", r["influx3"], r["influx3"]["queries"], r["influx3"]["disk"])' "$RUN/results.json"
log "all tests passed"
