#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

cluster_exists || fail "cluster $CLUSTER missing, run scripts/setup.sh first"
if [ "$#" -gt 0 ]; then
  psql_exec "$@"
else
  k exec -it postgres-0 -- psql -U "$DB_USER" -d "$DB_NAME"
fi
