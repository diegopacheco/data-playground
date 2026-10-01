#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require awk
require shasum
require curl

for f in files_before.tsv files_after.tsv readers.tsv; do
  [ -f "$RESULTS_DIR/$f" ] || fail "missing results/$f, run scripts/start-all.sh first"
done

expected="$RUN/expected.tsv"
awk -F, 'NR>1 && NF>=6 {n[$4]++; u[$4]+=$5; r[$4]+=$5*$6} END {for (c in n) printf "%s\t%d\t%d\t%.2f\n", c, n[c], u[c], r[c]}' "$ORDERS_CSV" | LC_ALL=C sort >"$expected"
log "awk expected aggregates from data/orders.csv"
cat "$expected"

for format in $FORMATS; do
  diff "$expected" "$RESULTS_DIR/agg_$format.tsv" >/dev/null || fail "$format aggregates differ from awk: $(diff "$expected" "$RESULTS_DIR/agg_$format.tsv" | head -5)"
  log "PASS $format aggregates identical to awk"
done

rows="$(awk 'NR>1 && NF' "$ORDERS_CSV" | wc -l | tr -d ' ')"
bad_rows="$(awk -F'\t' -v n="$rows" '$2!=n' "$RESULTS_DIR/readers.tsv")"
[ -z "$bad_rows" ] || fail "row count differs from csv ($rows): $bad_rows"
log "PASS every format returns $rows rows"

for format in delta iceberg; do
  cmp -s "$RESULTS_DIR/datafiles_hudi.txt" "$RESULTS_DIR/datafiles_$format.txt" || fail "$format reads different parquet files than hudi"
done
log "PASS hudi, delta and iceberg read the same $(wc -l <"$RESULTS_DIR/datafiles_hudi.txt" | tr -d ' ') parquet files"

missing="$(LC_ALL=C comm -23 <(LC_ALL=C sort "$RESULTS_DIR/files_before.tsv") <(LC_ALL=C sort "$RESULTS_DIR/files_after.tsv"))"
[ -z "$missing" ] || fail "files changed or removed by sync: $missing"
log "PASS all $(wc -l <"$RESULTS_DIR/files_before.tsv" | tr -d ' ') files that existed before sync are byte-identical after sync"

added="$(LC_ALL=C comm -13 <(LC_ALL=C sort "$RESULTS_DIR/files_before.tsv") <(LC_ALL=C sort "$RESULTS_DIR/files_after.tsv") | cut -f1)"
[ -n "$added" ] || fail "sync added no files"
not_meta="$(printf "%s\n" "$added" | grep -v -E '^(_delta_log|metadata)/' || true)"
[ -z "$not_meta" ] || fail "sync added files outside metadata dirs: $not_meta"
log "PASS sync added $(printf "%s\n" "$added" | wc -l | tr -d ' ') files, all under _delta_log/ or metadata/"
printf "%s\n" "$added" | grep -q '^_delta_log/.*\.json$' || fail "no delta commit json added"
printf "%s\n" "$added" | grep -q '^metadata/.*metadata\.json$' || fail "no iceberg metadata json added"
log "PASS delta commit json and iceberg metadata json exist"

parquet_before="$(awk -F'\t' '$1 ~ /\.parquet$/ && $1 !~ /^\.hoodie\// {print $1}' "$RESULTS_DIR/files_before.tsv" | LC_ALL=C sort)"
[ "$parquet_before" = "$(LC_ALL=C sort "$RESULTS_DIR/datafiles_hudi.txt")" ] || fail "readers do not read exactly the parquet files hudi wrote"
log "PASS the files every reader scans are exactly the parquet files spark wrote through hudi"

host="$RUN/host_files.tsv"
(cd "$LAKE_TABLE" && find . -type f | sed 's#^\./##' | LC_ALL=C sort | while IFS= read -r f; do printf "%s\t%s\t%s\n" "$f" "$(wc -c <"$f" | tr -d ' ')" "$(shasum -a 256 "$f" | cut -d' ' -f1)"; done) >"$host"
cmp -s "$host" <(LC_ALL=C sort "$RESULTS_DIR/files_after.tsv") || fail "host listing of lake/orders differs from results/files_after.tsv"
log "PASS host-side shasum listing matches the recorded after-sync listing"

if port_up "$(service_port ui)"; then
  api="$(curl -sf "$(service_url ui)/api/readers")" || fail "api /api/readers failed"
  count="$(printf "%s" "$api" | grep -o '"format":' | wc -l | tr -d ' ')"
  [ "$count" = "3" ] || fail "api returned $count readers"
  curl -sf "$(service_url ui)/api/files" | grep -q '"removed":0' || fail "api /api/files reports removed files"
  log "PASS ui api serves 3 readers and 0 removed files"
fi

log "all tests passed"
