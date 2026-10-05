#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

[ -x "$VENV/bin/python" ] || fail "venv missing, run ./scripts/setup.sh first"

log "running SQLMesh and dbt benchmark"
bash "$ROOT/bench/run.sh" || fail "benchmark pipeline failed, see $LOGS"

log "checking results"
( cd "$ROOT/bench" && "$VENV/bin/python" assertions.py ) || fail "assertions failed"

log "awk revenue_by_category"
bash "$ROOT/bench/awk_revenue_by_category.sh" | tee "$RUN/awk.csv"
for tool in sqlmesh dbt; do
  "$VENV/bin/python" -c "import json,sys; [print(f\"{r['category']},{r['total_orders']},{r['total_quantity']},{r['total_revenue']:.2f}\") for r in json.load(open(sys.argv[1]))['results'][sys.argv[2]]['revenue_by_category']]" "$ROOT/comparison.json" "$tool" >"$RUN/$tool.csv"
  diff "$RUN/awk.csv" "$RUN/$tool.csv" >/dev/null || fail "$tool revenue_by_category differs from awk"
  log "PASS $tool revenue_by_category matches awk"
done

port="$(service_port ui)"
if port_up "$port"; then
  curl -fs "$(service_url ui)/api/comparison" | "$VENV/bin/python" -c "import json,sys; d=json.load(sys.stdin); sys.exit(0 if d['checks']['results_identical'] else 1)" || fail "ui api did not serve comparison.json"
  log "PASS ui serves /api/comparison"
fi

log "tests passed"
