#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require curl
require podman
port_up "$(service_port ui)" || fail "ui is down, run scripts/start-all.sh first"

CUSTOMERS="$ROOT/data/customers.csv"
ORDERS="$ROOT/data/orders.csv"
API="$(service_url ui)/api"
ALL="1 2 3 4 5 6 7 8"
SUPPORT="1 2 3 5 6"
PII="1 3 4 5 6"
PASSED=0

customers() {
  awk -F, -v mode="$1" -v country="$2" -v cols="$3" -v limit="$4" -v email="${5:-****}" '
    function last4(s,   out, i) { out = ""; for (i = 4; i < length(s); i++) out = out "*"; return out substr(s, length(s) - 3) }
    NR == 1 || (country != "" && $6 != country) { next }
    n >= limit { exit }
    {
      n++
      if (mode == "masked") {
        if (email == "NULL") $3 = "NULL"; else sub(/^[^@]+/, email, $3)
        $4 = last4($4); $5 = "NULL"; $7 = last4($7)
      }
      k = split(cols, c, " "); line = ""
      for (i = 1; i <= k; i++) line = line (i > 1 ? "|" : "") $(c[i])
      print line
    }' "$CUSTOMERS"
}

joined() {
  customers "$1" "$2" "1 3 4 6" 999 | awk -F, 'NR == FNR { if (FNR > 1) { n[$2]++; a[$2] += $5 } next }
    { split($0, c, "|"); if (c[1] in n) printf "%s|%d|%.2f\n", $0, n[c[1]], a[c[1]] }' "$ORDERS" - | head -3
}

orders_total() {
  awk -F, -v country="$1" 'NR > 1 && (country == "" || $3 == country) { n++; a += $5 } END { printf "%d|%.2f\n", n, a }' "$ORDERS"
}

distinct() {
  customers "$1" "$2" "$3" 999 | awk '$0 != "NULL"' | sort -u | wc -l | tr -d ' '
}

counts() {
  printf "%s|%s|%s|%s\n" "$(customers "$1" "$2" 1 999 | wc -l | tr -d ' ')" "$(distinct "$1" "$2" 3)" "$(distinct "$1" "$2" 4)" "$(distinct "$1" "$2" 5)"
}

suffix_matches() {
  customers raw "$1" 4 999 | grep -c '0007$' || true
}

rows() {
  curl -sf "$API/compare?case=$1" >"$RUN/case.json" || fail "GET /api/compare?case=$1 failed"
  "$PY" -c 'import json,sys
r = json.load(open(sys.argv[1]))["results"][sys.argv[2]]
if "error" in r: print("ERROR " + r["error"])
for row in r.get("rows", []): print("|".join("NULL" if v is None else str(v) for v in row))' "$RUN/case.json" "$2"
}

check() {
  if [ "$2" = "$3" ]; then
    PASSED=$((PASSED + 1))
    log "PASS $1"
  else
    printf "FAIL %s\nexpected:\n%s\nactual:\n%s\n" "$1" "$2" "$3" >&2
    exit 1
  fi
}

check_denied() {
  case "$2" in
    "ERROR Access Denied"*) PASSED=$((PASSED + 1)); log "PASS $1" ;;
    *) printf "FAIL %s\nexpected an Access Denied error, actual:\n%s\n" "$1" "$2" >&2; exit 1 ;;
  esac
}

opa_tests="$(podman run --rm -v "$ROOT/opa:/s5:ro,Z" "$OPA_IMAGE" test /s5/policy /s5/tests 2>&1)" || fail "opa test failed: $opa_tests"
check "opa test: every rego unit test passes" "" "$(printf "%s\n" "$opa_tests" | grep -E '^(FAIL|ERROR)' || true)"
log "opa test: $(printf "%s\n" "$opa_tests" | tail -1)"

check "explicit columns as alice (admin) are the raw csv rows" "$(customers raw "" "$ALL" 3)" "$(rows columns alice)"
check "explicit columns as bruno (analyst) match awk masks: email ****@domain, id and card last 4, phone NULL" "$(customers masked "" "$ALL" 3)" "$(rows columns bruno)"
check "explicit columns as rita (regional analyst) are masked and only country BR" "$(customers masked BR "$ALL" 3)" "$(rows columns rita)"
check_denied "explicit columns as sam (support) are denied because national_id, credit_card and balance are hidden" "$(rows columns sam)"
check "explicit columns as mallory (unknown) are denied before the query starts" "ERROR Access Denied: Cannot execute query" "$(rows columns mallory)"

check "select * as bruno returns the same masked rows" "$(customers masked "" "$ALL" 3)" "$(rows star bruno)"
check "select * as sam silently drops the 3 hidden columns and keeps contact data raw" "$(customers raw "" "$SUPPORT" 3)" "$(rows star sam)"
check_denied "select * as mallory is denied" "$(rows star mallory)"

check "join as alice matches an awk join over both csv files" "$(joined raw "")" "$(rows join alice)"
check "join as bruno keeps the masks on the joined columns" "$(joined masked "")" "$(rows join bruno)"
check "join as rita is masked and both sides are filtered to BR" "$(joined masked BR)" "$(rows join rita)"
check_denied "join as sam is denied because it reads national_id" "$(rows join sam)"

check "orders total as alice is every order" "$(orders_total "")" "$(rows orders alice)"
check "orders total as rita only counts BR orders (row filter on orders)" "$(orders_total BR)" "$(rows orders rita)"

check "where email = raw value as alice finds the customer" "1" "$(rows where_raw alice)"
check "where email = raw value as bruno finds nothing: the predicate runs on the masked value" "0" "$(rows where_raw bruno)"
check "where national_id like visible suffix as bruno still matches as many rows as alice (partial mask leaks the suffix)" "$(suffix_matches "")" "$(rows where_suffix bruno)"
check "where national_id like visible suffix as rita only counts BR" "$(suffix_matches BR)" "$(rows where_suffix rita)"

check "count(distinct) as alice counts raw values" "$(counts raw "")" "$(rows distinct alice)"
check "count(distinct) as bruno counts masked values" "$(counts masked "")" "$(rows distinct bruno)"
check "count(distinct) as rita counts masked values of BR" "$(counts masked BR)" "$(rows distinct rita)"

check "security invoker view as bruno is masked" "$(customers masked "" "$PII" 3)" "$(rows view_invoker bruno)"
check "security invoker view as rita is masked and filtered" "$(customers masked BR "$PII" 3)" "$(rows view_invoker rita)"
check "LEAK security definer view owned by admin returns raw rows to bruno" "$(customers raw "" "$PII" 3)" "$(rows view_definer bruno)"
check "LEAK security definer view owned by admin returns every country raw to rita" "$(customers raw "" "$PII" 3)" "$(rows view_definer rita)"
check_denied "views in the scratch catalog are denied to sam" "$(rows view_definer sam)"

check "create table as by bruno persists the masked values, read back by alice" "$(customers masked "" "$PII" 3)" "$(rows ctas bruno)"
check "create table as by rita persists masked BR rows only, read back by alice" "$(customers masked BR "$PII" 3)" "$(rows ctas rita)"
check_denied "create table as by sam is denied" "$(rows ctas sam)"
check "LEAK copy made by admin has no policy entry and returns raw rows to bruno" "$(customers raw "" "$PII" 3)" "$(rows admin_copy bruno)"

started="$(trino_started)"
rm -rf "$RUN/policy-edit"
cp -R "$ROOT/opa/policy" "$RUN/policy-edit"
sed 's/"email": "email"/"email": "null"/' "$ROOT/opa/policy/pii/data.json" >"$RUN/policy-edit/pii/data.json"
"$SCRIPTS/reload-policy.sh" "$RUN/policy-edit"
check "data change: email mask kind null takes effect on the next query" "$(customers masked "" "$ALL" 3 NULL)" "$(rows columns bruno)"
cp "$ROOT/opa/policy/pii/data.json" "$RUN/policy-edit/pii/data.json"
sed "s/'\*\*\*\*'/'hidden'/" "$ROOT/opa/policy/trino.rego" >"$RUN/policy-edit/trino.rego"
"$SCRIPTS/reload-policy.sh" "$RUN/policy-edit"
check "rego change: email mask text hidden takes effect on the next query" "$(customers masked "" "$ALL" 3 hidden)" "$(rows columns bruno)"
"$SCRIPTS/reload-policy.sh"
check "policy restored from the repository files" "$(customers masked "" "$ALL" 3)" "$(rows columns bruno)"
check "trino container start time did not change across 3 policy reloads" "$started" "$(trino_started)"

curl -sf "$API/decisions?user=rita" >"$RUN/decisions.json" || fail "GET /api/decisions failed"
decision() {
  "$PY" -c 'import json,sys
d = json.load(open(sys.argv[1]))
hits = [x for x in d["decisions"] if x["path"] == sys.argv[2] and x["input"]["context"]["identity"]["user"] == "rita"]
print(json.dumps(hits[0]["result"], sort_keys=True) if hits else "no decision")' "$RUN/decisions.json" "$1"
}
check "decision log holds the row filter opa returned to trino for rita" '[{"expression": "country = '"'"'BR'"'"'"}]' "$(decision trino/rowFilters)"
masked_columns() {
  "$PY" -c 'import json,sys
d = json.load(open(sys.argv[1]))
batch = [x for x in d["decisions"] if x["path"] == "trino/batchColumnMasks"][0]
asked = batch["input"]["action"]["filterResources"]
print(len(asked), " ".join(sorted(asked[m["index"]]["column"]["columnName"] for m in batch["result"])))' "$RUN/decisions.json"
}
check "decision log shows trino asked for all 8 columns in one batch and opa masked the 4 pii ones" "8 credit_card email national_id phone" "$(masked_columns)"
log "decision log: $("$PY" -c 'import json,sys; print(len(json.load(open(sys.argv[1]))["decisions"]))' "$RUN/decisions.json") opa decisions for one query"

log "measured: customers|distinct emails|distinct national ids|distinct phones"
log "  alice $(rows distinct alice)"
log "  bruno $(rows distinct bruno)"
log "  rita  $(rows distinct rita)"
log "all $PASSED checks passed"
