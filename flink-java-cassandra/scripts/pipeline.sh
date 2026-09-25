#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require java
[ -d "$ROOT/target/lib" ] || build_app
cql_ready || fail "cassandra is not ready, run ./scripts/start-all.sh first"

log "running flink pipeline on $ROOT/data/orders.csv"
java -cp "$CLASSPATH_APP" com.github.diegopacheco.flinkcassandra.Pipeline "$ROOT/data/orders.csv" >"$LOGS/pipeline.log" 2>&1 || fail "pipeline failed, see $LOGS/pipeline.log"
log "pipeline finished, results written to sales.revenue_by_category"
