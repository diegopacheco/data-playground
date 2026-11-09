#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

log "java unit tests"
(cd "$ROOT/java-loader" && mvn -q -B test) || fail "java unit tests failed"

log "python unit tests and type check"
(cd "$ROOT/python-loader" && uv run --python 3.15 pytest -q && uv run --python 3.15 ty check) || fail "python unit tests failed"

port_up "$(service_port postgres)" || fail "postgres is DOWN, run scripts/start-all.sh first"

log "end to end tests against $CLUSTER"
(cd "$ROOT/e2e" && uv run --python 3.15 ty check && \
  KUBE_CONTEXT="$CTX" DB_PORT="$(service_port postgres)" uv run --python 3.15 pytest -v) || fail "end to end tests failed"

log "batch results"
psql_exec -c "
SELECT job,
       CASE WHEN runner LIKE 'manual-%' THEN 'manual' ELSE 'cron' END AS trigger,
       count(*) AS runs,
       sum(rows_loaded) AS rows_total,
       round(avg(rows_loaded)) AS rows_avg,
       max(rows_loaded) AS rows_max,
       round(avg(duration_ms)) AS ms_avg,
       percentile_disc(0.5) WITHIN GROUP (ORDER BY duration_ms) AS ms_p50,
       max(duration_ms) AS ms_max
FROM batch_runs GROUP BY 1, 2 ORDER BY 1, 2" || fail "results query failed"
log "all tests passed"
