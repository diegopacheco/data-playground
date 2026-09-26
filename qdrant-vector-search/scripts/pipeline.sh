#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require podman-compose
port_up "$(service_port qdrant)" || fail "qdrant is down, run scripts/start-all.sh first"

log "embedding data/products.csv and upserting into qdrant"
compose run --rm q6-loader 2>/dev/null || fail "loader failed, rerun: podman-compose run --rm q6-loader"
