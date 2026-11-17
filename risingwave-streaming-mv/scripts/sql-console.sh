#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require podman
port_up "$(service_port risingwave)" || fail "risingwave is down, run scripts/start-all.sh first"
podman image exists "$PSQL_IMAGE" || fail "image $PSQL_IMAGE missing, run scripts/setup.sh first"
podman run --rm -it --network t1-net "$PSQL_IMAGE" psql -h t1-risingwave -p 4566 -U root -d dev "$@"
