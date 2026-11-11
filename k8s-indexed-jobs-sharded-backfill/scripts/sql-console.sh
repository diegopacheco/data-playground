#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

cluster_exists || fail "cluster $CLUSTER missing, run scripts/setup.sh first"
postgres_ready || fail "postgres is not running, run scripts/start-all.sh first"
if [ -t 0 ]; then
  k exec -it deploy/postgres -- psql -U backfill -d backfill "$@"
else
  k exec -i deploy/postgres -- psql -U backfill -d backfill "$@"
fi
