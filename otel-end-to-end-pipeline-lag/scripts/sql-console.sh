#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

cluster_exists || fail "cluster $CLUSTER missing, run scripts/setup.sh first"
pods_ready -l app=postgres || fail "postgres not ready, run scripts/setup.sh first"
k exec -it deploy/postgres -- psql -U pipeline -d pipeline "$@"
