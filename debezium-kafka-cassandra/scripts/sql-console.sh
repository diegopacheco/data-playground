#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

target="${1:-mysql}"
case "$target" in
  mysql)
    port_up "$(service_port mysql)" || fail "mysql is not running, run ./scripts/start-all.sh first"
    podman exec -it "$MYSQL_CONTAINER" mysql -uroot -proot sales ;;
  cassandra)
    port_up "$(service_port cassandra)" || fail "cassandra is not running, run ./scripts/start-all.sh first"
    podman exec -it "$CASSANDRA_CONTAINER" cqlsh -k sales ;;
  *)
    fail "usage: sql-console.sh [mysql|cassandra]" ;;
esac
