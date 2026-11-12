#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

cluster_exists || fail "cluster $CLUSTER missing, run scripts/setup.sh first"
port_up "$(service_port lab)" || fail "lab is not forwarded, run scripts/start-all.sh first"
(cd "$ROOT/e2e" && e2e_env uv run python -m coldstart.bench "${1:-5}") || fail "benchmark failed"
