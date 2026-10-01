#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require sqlite3
[ -f "$STORE_DB" ] || fail "store not found at state/store.db, run ./scripts/start-all.sh first"

sqlite3 -header -column "$STORE_DB" "$@"
