#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require curl
port_up "$(service_port ui)" || fail "ui is down, run scripts/start-all.sh first"

IDS="$RUN/ids"
PROBES="$RUN/probe-queries.txt"
QDRANT="$(service_url qdrant)/collections/items"
passed=0

check() {
  if [ "$2" = "$3" ]; then
    log "PASS $1"
    passed=$((passed + 1))
  else
    printf "FAIL %s\nexpected:\n%s\nactual:\n%s\n" "$1" "$2" "$3" >&2
    exit 1
  fi
}

at_least() {
  if awk -v a="$2" -v b="$3" 'BEGIN { exit !(a + 0 >= b + 0) }'; then
    log "PASS $1 ($2 >= $3)"
    passed=$((passed + 1))
  else
    printf "FAIL %s: %s is below %s\n" "$1" "$2" "$3" >&2
    exit 1
  fi
}

below() {
  if awk -v a="$2" -v b="$3" 'BEGIN { exit !(a + 0 < b + 0) }'; then
    log "PASS $1 ($2 < $3)"
    passed=$((passed + 1))
  else
    printf "FAIL %s: %s is not below %s\n" "$1" "$2" "$3" >&2
    exit 1
  fi
}

recall() {
  awk -v k="$K" 'NR == FNR { for (i = 1; i <= NF; i++) truth[FNR, $i] = 1; next }
    { for (i = 1; i <= NF; i++) if ((FNR, $i) in truth) hit++; n++ }
    END { printf "%.4f\n", hit / (n * k) }' "$1" "$2"
}

sorted() {
  local line
  while IFS= read -r line; do
    printf "%s\n" $line | sort -n | tr '\n' ' ' | sed 's/ $//'
    printf "\n"
  done
}

pg_probe() {
  { printf "%s\n" "$1"; awk -v k="$K" '{ printf "SELECT string_agg(id::text, \x27 \x27 ORDER BY id) FROM (SELECT id FROM items ORDER BY embedding <-> \x27[%s]\x27 LIMIT %d) t;\n", $0, k }' "$PROBES"; } |
    podman exec -i s9-postgres psql -U bench -d bench -v ON_ERROR_STOP=1 -At -q
}

qdrant_probe() {
  local q
  while IFS= read -r q; do
    curl -sf -X POST "$QDRANT/points/query" -H "Content-Type: application/json" -d "{\"query\":[$q],\"limit\":$K,\"params\":$1}" |
      grep -o '"id":[0-9]*' | cut -d: -f2 | sorted_column
  done <"$PROBES"
}

sorted_column() {
  sort -n | tr '\n' ' ' | sed 's/ $//'
  printf "\n"
}

value() {
  printf "%s\n" "$flat" | awk -v a="$1" -v b="$2" -v c="${3:-}" '$1 == a && $2 == b && (c == "" || $3 == c) { print $NF; exit }'
}

results="$(curl -sf "$(service_url ui)/api/results")" || fail "GET /api/results failed"
flat="$(printf "%s" "$results" | "$PY" -c 'import json,sys
r = json.load(sys.stdin)
for k in ("rows", "k", "m", "ef_construction", "bucket", "filtered_ef"): print("setting", k, r["settings"][k])
for e in r["engines"]:
    for s in e["sweep"]: print("sweep", e["name"], s["ef"], "%.4f" % s["recall"])
    for f in e["filtered"]: print("filtered", f["file"], "%.3f" % f["returned"], "%.4f" % f["recall"])
    print("plan", e["name"], e["plan"].replace("\n", " ").split(" <- ")[-1].split()[0])')"

ROWS="$(value setting rows)"
K="$(value setting k)"
M="$(value setting m)"
EFC="$(value setting ef_construction)"
BUCKET="$(value setting bucket)"
ENGINES="$(printf "%s\n" "$flat" | awk '$1 == "plan" { print $2 }')"
EFS="$(printf "%s\n" "$flat" | awk '$1 == "sweep" && $2 == "pgvector" { print $3 }')"
LAST="$(printf "%s\n" "$EFS" | tail -1)"
FIRST="$(printf "%s\n" "$EFS" | head -1)"

log "ground truth: numpy brute force against two other exact scans"
head -20 "$IDS/truth.txt" | sorted >"$RUN/truth-probes.txt"
pg_probe "SET enable_indexscan = off;" >"$RUN/pg-exact.txt" || fail "postgres exact scan failed"
qdrant_probe '{"exact":true}' >"$RUN/qdrant-exact.txt" || fail "qdrant exact search failed"
check "numpy top-$K equals postgres sequential scan top-$K on 20 queries" "$(cat "$RUN/truth-probes.txt")" "$(cat "$RUN/pg-exact.txt")"
check "numpy top-$K equals qdrant exact=true top-$K on 20 queries" "$(cat "$RUN/truth-probes.txt")" "$(cat "$RUN/qdrant-exact.txt")"

log "reported recall recomputed with awk from the raw ids each engine returned"
for engine in $ENGINES; do
  for ef in $EFS; do
    check "$engine ef $ef recall@$K matches awk" "$(recall "$IDS/truth.txt" "$IDS/$engine-ef$ef.txt")" "$(value sweep "$engine" "$ef")"
  done
  below "$engine recall grows with ef, ef $FIRST against ef $LAST" "$(value sweep "$engine" "$FIRST")" "$(value sweep "$engine" "$LAST")"
  at_least "$engine recall@$K at ef $LAST" "$(value sweep "$engine" "$LAST")" 0.99
done

log "same data and same hnsw settings in every engine"
info="$(curl -sf "$QDRANT")" || fail "GET qdrant collection failed"
has() {
  check "$1" "$2" "$(printf "%s" "$info" | grep -o "$2" | head -1)"
}
check "postgres holds $ROWS rows" "$ROWS" "$(psql_exec -At -c 'SELECT count(*) FROM items')"
has "qdrant holds $ROWS points" "\"points_count\":$ROWS"
has "qdrant hnsw index covers every point" "\"indexed_vectors_count\":$ROWS"
has "qdrant collection is green" '"status":"green"'
has "qdrant m" "\"m\":$M"
has "qdrant ef_construct" "\"ef_construct\":$EFC"
has "qdrant quantization is off" '"quantization_config":null'
check "postgres hnsw index definition" "CREATE INDEX items_hnsw ON public.items USING hnsw (embedding vector_l2_ops) WITH (m='$M', ef_construction='$EFC')" "$(psql_exec -At -c "SELECT indexdef FROM pg_indexes WHERE indexname = 'items_hnsw'")"
check "duckdb plan reads from HNSW_INDEX_SCAN" "HNSW_INDEX_SCAN" "$(value plan duckdb-vss)"
rounded() {
  tr -d '[]' | tr ',' '\n' | awk '{ printf "%.5g\n", $1 }'
}
check "vector 4242 is identical in postgres and qdrant" "$(psql_exec -At -c 'SELECT embedding FROM items WHERE id = 4242' | rounded)" "$(curl -sf "$QDRANT/points/4242" | grep -o '"vector":\[[^]]*\]' | cut -d: -f2 | rounded)"

log "the indexes are really used, live queries"
probe="$(head -1 "$PROBES")"
plan="$(psql_exec -At -c "EXPLAIN (COSTS OFF) SELECT id FROM items ORDER BY embedding <-> '[$probe]' LIMIT $K")"
check "postgres EXPLAIN uses the hnsw index" "Index Scan using items_hnsw on items" "$(printf "%s\n" "$plan" | grep -o 'Index Scan using items_hnsw on items')"
plan="$(psql_exec -At -c "EXPLAIN (COSTS OFF) SELECT id FROM items WHERE bucket = $BUCKET ORDER BY embedding <-> '[$probe]' LIMIT $K")"
check "postgres filtered EXPLAIN uses the hnsw index" "Index Scan using items_hnsw on items" "$(printf "%s\n" "$plan" | grep -o 'Index Scan using items_hnsw on items')"
pg_probe "SET hnsw.ef_search = $LAST;" >"$RUN/pg-live.txt" || fail "postgres hnsw search failed"
qdrant_probe "{\"hnsw_ef\":$LAST}" >"$RUN/qdrant-live.txt" || fail "qdrant hnsw search failed"
at_least "postgres live hnsw recall@$K at ef $LAST against its own exact scan" "$(recall "$RUN/pg-exact.txt" "$RUN/pg-live.txt")" 0.95
at_least "qdrant live hnsw recall@$K at ef $LAST against its own exact search" "$(recall "$RUN/qdrant-exact.txt" "$RUN/qdrant-live.txt")" 0.95

log "filtered search, bucket = $BUCKET"
for row in $(printf "%s\n" "$flat" | awk '$1 == "filtered" { print $2 }'); do
  check "$row recall@$K matches awk" "$(recall "$IDS/truth-filtered.txt" "$IDS/$row.txt")" "$(value filtered "$row")"
  check "$row returns only bucket $BUCKET" "0" "$(awk -v b="$BUCKET" 'NR == FNR { bucket[$1] = $2; next } { for (i = 1; i <= NF; i++) if (bucket[$i] != b) bad++ } END { print bad + 0 }' "$IDS/buckets.txt" "$IDS/$row.txt")"
done
returned() {
  printf "%s\n" "$flat" | awk -v f="$1" '$1 == "filtered" && $2 == f { print $3 }'
}
below "duckdb vss filters after the index scan and returns fewer than $K rows" "$(returned duckdb-vss-filtered0)" "$K"
below "duckdb vss filtered recall collapses" "$(value filtered duckdb-vss-filtered0)" 0.5
below "pgvector without iterative scan returns fewer than $K rows" "$(returned pgvector-filtered0)" "$K"
below "pgvector iterative scan off recall is below strict_order" "$(value filtered pgvector-filtered0)" "$(value filtered pgvector-filtered1)"
at_least "pgvector iterative scan strict_order filtered recall" "$(value filtered pgvector-filtered1)" 0.99
at_least "qdrant filtered recall" "$(value filtered qdrant-filtered0)" 0.99

log "recall@$K per engine and ef (engine ef recall):"
printf "%s\n" "$flat" | awk '$1 == "sweep" { print $2, $3, $4 }'
log "filtered recall@$K (run returned recall):"
printf "%s\n" "$flat" | awk '$1 == "filtered" { print $2, $3, $4 }'
log "all $passed checks passed"
