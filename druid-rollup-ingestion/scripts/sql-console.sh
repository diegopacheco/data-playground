#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require curl
require python3
port_up "$(service_port broker)" || fail "druid broker is down, run scripts/start-all.sh first"

run() {
  druid_sql "$1" csv || printf "query failed\n" >&2
  printf "\n"
}

if [ "$#" -gt 0 ]; then
  run "$*"
  exit 0
fi

log "Druid SQL on $(service_url broker)/druid/v2/sql, one query per line, empty line or ctrl-d to quit"
while IFS= read -r -p "druid> " query; do
  [ -z "$query" ] && break
  run "$query"
done
