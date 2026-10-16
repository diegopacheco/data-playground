#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

engine="${1:-timescaledb}"
[ "$#" -eq 0 ] || shift
port_up "$(service_port timescaledb)" || fail "the stack is down, run scripts/start-all.sh first"

case "$engine" in
  timescaledb) exec podman exec -it s7-timescaledb psql -U s7 -d s7 "$@" ;;
  questdb) exec podman exec -it -e PGPASSWORD=quest s7-timescaledb psql -h s7-questdb -p 8812 -U admin -d qdb "$@" ;;
  influx3) [ "$#" -gt 0 ] || fail "usage: sql-console.sh influx3 \"SELECT ...\""
    exec podman exec s7-influx3 influxdb3 query --database s7 "$@" ;;
  *) fail "unknown engine $engine, use timescaledb, questdb or influx3" ;;
esac
