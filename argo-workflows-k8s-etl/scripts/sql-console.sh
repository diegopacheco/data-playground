#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

cluster_exists || fail "cluster $CLUSTER is DOWN, run scripts/start-all.sh first"
k -n "$NAMESPACE" exec -it deployment/t8-postgres -- psql -U etl -d etl "$@"
