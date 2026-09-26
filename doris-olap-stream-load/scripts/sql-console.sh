#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

port="$(service_port mysql)"
port_up "$port" || fail "doris is not running on $port, run ./scripts/start-all.sh first"

if command -v mysql >/dev/null 2>&1; then
  exec mysql -h127.0.0.1 -P"$port" -uroot sales "$@"
elif [ -t 0 ]; then
  exec podman exec -it "$FE_CONTAINER" mysql -h127.0.0.1 -P9030 -uroot sales "$@"
else
  exec podman exec -i "$FE_CONTAINER" mysql -h127.0.0.1 -P9030 -uroot sales "$@"
fi
