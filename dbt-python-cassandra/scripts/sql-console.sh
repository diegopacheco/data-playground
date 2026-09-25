#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

podman container exists p5-cassandra || fail "cassandra is down, run scripts/start-all.sh first"
exec podman exec -it p5-cassandra cqlsh -k sales "$@"
