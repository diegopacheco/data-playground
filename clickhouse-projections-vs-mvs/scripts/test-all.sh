#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require curl
require awk
port_up "$(service_port ui)" || fail "ui is down, run scripts/start-all.sh first"
clickhouse_ready >/dev/null 2>&1 || fail "clickhouse is down, run scripts/start-all.sh first"

EXPECTED="$RUN/expected.txt"
GROUPED="SELECT toDate(ts) AS day, country, device, count() AS events, sum(amount) AS revenue, max(amount) AS max_amount FROM %s GROUP BY day, country, device"
MERGED="SELECT day, country, device, countMerge(events) AS events, sumMerge(amount_sum) AS revenue, maxMerge(amount_max) AS max_amount FROM bench.daily_totals GROUP BY day, country, device"
FINAL="SELECT day, country, device, finalizeAggregation(events) AS events, finalizeAggregation(amount_sum) AS revenue, finalizeAggregation(amount_max) AS max_amount FROM bench.daily_totals FINAL"
BY_EVENT_TYPE="SELECT event_type, count(), sum(amount) FROM %s GROUP BY event_type"

setting() {
  "$PY" -c 'import sys
sys.path.insert(0, sys.argv[1])
import events
value = getattr(events, sys.argv[2])
print(" ".join(value) if isinstance(value, list) else value)' "$ROOT/app" "$1"
}

recorded() {
  printf "%s" "$results" | "$PY" -c 'import json, sys
print(eval(sys.argv[1], {"r": json.load(sys.stdin)}))' "$1"
}

independent() {
  awk -v seed="$(setting SEED)" -v prime="$(setting PRIME)" -v total="$(setting TOTAL_ROWS)" -v historic="$(setting HISTORIC_ROWS)" \
    -v span="$(setting SPAN_SECONDS)" -v countries="$(setting COUNTRIES)" -v devices="$(setting DEVICES)" -v types="$(setting EVENT_TYPES)" 'BEGIN {
      nc = split(countries, C, " "); nd = split(devices, D, " "); nt = split(types, T, " ")
      for (n = 0; n < total; n++) {
        x = ((n + 1) * 48271 + seed) % prime
        h1 = (x * x + n) % prime
        h2 = (h1 * 40503 + x) % prime
        country = C[h1 % nc + 1]; device = D[int(h1 / 8) % nd + 1]; type = T[int(h1 / 32) % nt + 1]
        amount = h2 % 19997 + 1
        e["full"]++; r["full"] += amount
        if (n >= historic) { e["live"]++; r["live"] += amount }
        if (country == "BR" && type == "refund") continue
        e["deleted"]++; r["deleted"] += amount
        if (device == "tablet" && type == "purchase") amount *= 2
        e["final"]++; r["final"] += amount
        key = int(int(n * span / total) / 86400) " " country " " device
        ge[key]++; gr[key] += amount
        if (amount > gm[key]) gm[key] = amount
      }
      for (k in e) printf "total %s %d %d\n", k, e[k], r[k]
      for (k in ge) printf "group %s %d %d %d\n", k, ge[k], gr[k], gm[k]
    }'
}

total() {
  awk -v n="$1" '$1 == "total" && $2 == n {print $3, $4}' "$EXPECTED"
}

stage() {
  recorded "' '.join(str(s[v][k]) for s in r['stages'] if s['id'] == '$1' for v in ('base', 'projection', 'view') for k in ('events', 'revenue'))"
}

groups() {
  ch -q "SELECT dateDiff('day', toDate('$(setting START)'), day), country, device, events, revenue, max_amount FROM ($1) FORMAT TSV" | tr '\t' ' ' | sort
}

logged() {
  local id
  id="s4-test-$$-$RANDOM"
  ch --query_id "$id" -q "$1 FORMAT Null"
  ch -q "SYSTEM FLUSH LOGS"
  ch -q "SELECT read_rows, arrayStringConcat(projections, ',') FROM system.query_log WHERE query_id = '$id' AND type = 'QueryFinish' FORMAT TSV" | tr '\t' ' ' | sed 's/ *$//'
}

target_answers() {
  if ch -q "$(printf "$BY_EVENT_TYPE" bench.daily_totals) FORMAT Null" >/dev/null 2>&1; then echo yes; else echo no; fi
}

passed=0
check() {
  if [ "$2" = "$3" ]; then
    log "PASS $1"
    passed=$((passed + 1))
  else
    printf "FAIL %s\nexpected:\n%s\nactual:\n%s\n" "$1" "$(printf "%s\n" "$2" | head -5)" "$(printf "%s\n" "$3" | head -5)" >&2
    exit 1
  fi
}

results="$(curl -sf "$(service_url ui)/api/results")" || fail "GET /api/results failed"

log "computing expected aggregates for $(setting TOTAL_ROWS) events with awk, independent of clickhouse"
independent >"$EXPECTED" || fail "awk calculation failed"
full="$(total full)"
live="$(total live)"
deleted="$(total deleted)"
final="$(total final)"
expected_groups="$(awk '$1 == "group" {print $2, $3, $4, $5, $6, $7}' "$EXPECTED" | sort)"
group_count="$(printf "%s\n" "$expected_groups" | wc -l | tr -d ' ')"
final_events="${final%% *}"

check "created late, the view misses the historic rows, the projection table still answers right" "$full $full $live" "$(stage before_backfill)"
check "after MATERIALIZE PROJECTION and manual INSERT SELECT all three match awk" "$full $full $full" "$(stage after_backfill)"
check "after ALTER DELETE plain and projection match awk, view target is stale" "$deleted $deleted $full" "$(stage after_delete)"
check "after ALTER UPDATE plain and projection match awk, view target is stale" "$final $final $full" "$(stage after_update)"
check "after rebuilding the view target all three match awk" "$final $final $final" "$(stage after_repair)"

check "live plain table groups match awk" "$expected_groups" "$(groups "$(printf "$GROUPED" bench.events_base)")"
check "live projection table groups match awk with the same SQL" "$expected_groups" "$(groups "$(printf "$GROUPED" bench.events_proj)")"
check "live view target groups match awk through -Merge combinators" "$expected_groups" "$(groups "$MERGED")"
check "live view target groups match awk through FINAL" "$expected_groups" "$(groups "$FINAL")"

check "query_log shows the projection served the unchanged SQL reading only pre-aggregated rows" "$group_count bench.events_proj.daily_totals" "$(logged "$(printf "$GROUPED" bench.events_proj)")"
check "query_log shows a grouping the projection lacks falls back to every base row" "$final_events" "$(logged "$(printf "$BY_EVENT_TYPE" bench.events_proj)")"
check "the plain table reads every row for the grouped query" "$final_events" "$(logged "$(printf "$GROUPED" bench.events_base)")"
check "the view target cannot answer a grouping it does not store" "no" "$(target_answers)"

check "recorded: served queries are faster than the plain table and read at most $group_count rows" "True" \
  "$(recorded "all(v['median_ms'] < c['variants'][0]['median_ms'] and v['read_rows'] <= $group_count for c in r['read'] if c['view_reads_target'] for v in c['variants'][1:])")"
check "recorded: unserved queries read the same rows as the plain table without a projection" "True" \
  "$(recorded "all(v['read_rows'] == c['variants'][0]['read_rows'] and not v['projections'] for c in r['read'] if not c['view_reads_target'] for v in c['variants'])")"
check "recorded: unmerged view target holds more rows than keys, FINAL collapses them" "True" \
  "$(recorded "r['merge_state']['rows_without_final'] > r['merge_state']['groups'] == r['merge_state']['rows_with_final']")"
check "recorded: projection and view both store $group_count pre-aggregated rows" "$group_count $group_count" \
  "$(recorded "' '.join(str(s['pre_aggregated_rows']) for s in r['storage'][1:])")"

log "write cost, reported and not asserted because it is a timing on a shared machine:"
recorded "'\n'.join('%-11s %.3f s %d rows/s' % (w['variant'], w['seconds'], w['rows_per_second']) for w in r['write'])"
log "read latency median / p95 in ms and rows read:"
recorded "'\n'.join('%-12s %-11s %8.2f %8.2f %9d' % (c['id'], v['variant'], v['median_ms'], v['p95_ms'], v['read_rows']) for c in r['read'] for v in c['variants'])"
log "$passed checks passed, 0 failed"
