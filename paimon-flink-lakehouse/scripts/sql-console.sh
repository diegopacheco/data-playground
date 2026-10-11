#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

[ -d "$ROOT/target/lib" ] || build_app

if [ "$#" -eq 0 ]; then
  set -- "SELECT * FROM revenue_by_category ORDER BY category" "SELECT COUNT(*) AS orders FROM orders"
fi
sql "$@" || fail "query failed, see $LOGS/sql.log"
