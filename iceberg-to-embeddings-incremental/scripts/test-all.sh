#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require curl
port_up "$(service_port ui)" || fail "ui is down, run scripts/start-all.sh first"

API="$(service_url ui)/api"
R1="$ROOT/data/round1-initial.csv"
R2="$ROOT/data/round2-append.csv"
R3="$ROOT/data/round3-update.csv"
R4="$ROOT/data/round4-delete.csv"

check() {
  if [ "$2" = "$3" ]; then
    log "PASS $1"
  else
    printf "FAIL %s\nexpected:\n%s\nactual:\n%s\n" "$1" "$2" "$3" >&2
    exit 1
  fi
}

data_rows() {
  awk 'NR>1' "$1" | wc -l | tr -d ' '
}

changed_ids() {
  awk -F, 'FNR==1{next} FILENAME==ARGV[3]{if (t[$1] != $0) print $1; next} {t[$1]=$0}' "$R1" "$R2" "$R3" | sort -n | tr '\n' ' '
}

final_rows() {
  awk -F, 'FNR==1{next} FILENAME==ARGV[4]{delete t[$1]; next} {t[$1]=$0} END{for (i in t) print t[i]}' "$R1" "$R2" "$R3" "$R4" | sort -t, -k1,1n
}

text_of() {
  awk -F, -v id="$1" 'FNR>1 && $1==id{print $3; exit}' "$R1" "$R2"
}

api_round() {
  printf "%s" "$rounds" | "$PY" -c 'import json,sys
r=[x for x in json.load(sys.stdin) if x["round"]==int(sys.argv[1])][0]
print(r["table_rows"], len(r["inserted"]), len(r["updated"]), len(r["deleted"]), r["rows_embedded"], r["model_calls"], r["vectors_after"])' "$1"
}

api_ids() {
  printf "%s" "$rounds" | "$PY" -c 'import json,sys
r=[x for x in json.load(sys.stdin) if x["round"]==int(sys.argv[1])][0]
print("".join("%d " % i for i in r[sys.argv[2]]), end="")' "$1" "$2"
}

search_ids() {
  curl -sf --get --data-urlencode "q=$1" --data-urlencode "k=$2" "$API/search" | "$PY" -c 'import json,sys
print(" ".join(str(r["id"]) for r in json.load(sys.stdin)))'
}

pg() {
  psql_exec -At -c "$1"
}

calls() {
  echo $((($1 + 15) / 16))
}

rounds="$(curl -sf "$API/rounds")" || fail "GET /api/rounds failed"

n1="$(data_rows "$R1")"
n2="$(data_rows "$R2")"
changed="$(changed_ids)"
u="$(printf "%s" "$changed" | wc -w | tr -d ' ')"
d="$(data_rows "$R4")"
t2=$((n1 + n2))
t4=$((t2 - d))

log "columns: table_rows inserted updated deleted rows_embedded model_calls vectors"
check "round 1 initial load embeds all $n1 rows" "$n1 $n1 0 0 $n1 $(calls "$n1") $n1" "$(api_round 1)"
check "round 2 append embeds only the $n2 appended rows of $t2" "$t2 $n2 0 0 $n2 $(calls "$n2") $t2" "$(api_round 2)"
check "round 3 update embeds only the $u changed rows of $t2" "$t2 0 $u 0 $u $(calls "$u") $t2" "$(api_round 3)"
check "round 4 delete embeds nothing and removes $d vectors" "$t4 0 0 $d 0 0 $t4" "$(api_round 4)"
check "round 5 no-op makes zero model calls" "$t4 0 0 0 0 0 $t4" "$(api_round 5)"
check "round 3 updated ids match awk, unchanged rows of the update file are skipped" "$changed" "$(api_ids 3 updated)"
check "round 4 deleted ids match the delete file" "$(awk 'NR>1' "$R4" | sort -n | tr '\n' ' ')" "$(api_ids 4 deleted)"

embedded=0
table_total=0
for n in 1 2 3 4 5; do
  set -- $(api_round "$n")
  embedded=$((embedded + $5))
  table_total=$((table_total + $1))
  if [ "$n" -gt 1 ] && [ "$5" -ge "$1" ]; then
    fail "round $n embedded $5 rows, not less than the table size $1"
  fi
  if [ "$5" -ne $(($2 + $3)) ]; then
    fail "round $n embedded $5 rows but the diff has $(($2 + $3)) inserted and updated rows"
  fi
done
log "PASS rows embedded equal inserted plus updated in every round and stay below the table size after the initial load"
check "total rows embedded over five rounds is the sum of the diffs" "$((n1 + n2 + u))" "$embedded"
log "full re-embed on every round would have embedded $table_total rows, incremental sync embedded $embedded"

check "vector store rows equal the final table computed by awk" "$(final_rows)" "$(pg "SELECT id || ',' || category || ',' || text FROM documents ORDER BY id")"

current="$(curl -sf "$REST_URI/v1/namespaces/library/tables/documents" | "$PY" -c 'import json,sys
print(json.load(sys.stdin)["metadata"]["current-snapshot-id"])')" || fail "rest catalog did not return the table"
check "watermark in postgres is the current iceberg snapshot" "$current" "$(pg "SELECT snapshot_id FROM sync_state WHERE name = 'documents'")"

log "full re-embed of the current table against the vector store, and file changelog against full snapshot comparison:"
"$PY" "$ROOT/app/verify.py" 2>"$RUN/logs/verify.log" || fail "vector store differs from a full re-embed, see .run/logs/verify.log"
log "PASS vector store equals a full re-embed and every diff equals a full snapshot comparison"

while IFS=, read -r id category text; do
  check "search finds appended row $id first" "$id" "$(search_ids "$text" 1)"
done < <(awk 'NR>1' "$R2")

for id in $changed; do
  check "search finds updated row $id by its new text" "$id" "$(search_ids "$(awk -F, -v id="$id" '$1==id{print $3}' "$R3")" 1)"
done

for id in $(awk 'NR>1' "$R4"); do
  check "search for the text of deleted row $id does not return it" "" "$(search_ids "$(text_of "$id")" 5 | tr ' ' '\n' | grep -x "$id" || true)"
done

telescope="$(awk -F, '/telescope/{print $1}' "$R2")"
columnar="$(awk -F, '/columnar/{print $1}' "$R1")"
grep -qx "$columnar" "$R4" || fail "row $columnar is expected in the delete file"
check "question about an infrared telescope returns appended row $telescope" "$telescope" "$(search_ids "infrared telescope studying planets around other stars" 1)"
check "question about columnar storage does not return deleted row $columnar" "" "$(search_ids "columnar storage for analytics" 5 | tr ' ' '\n' | grep -x "$columnar" || true)"

log "all tests passed"
