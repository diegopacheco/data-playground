#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

for name in $(service_names); do
  port="$(service_port "$name")"
  pid="$(port_pid "$port")"
  if [ -n "$pid" ]; then
    printf "%-10s %-6s UP   pid %-7s %s\n" "$name" "$port" "$pid" "$(service_url "$name")"
  else
    printf "%-10s %-6s DOWN\n" "$name" "$port"
  fi
done
for name in r7-zookeeper r7-bookie r7-broker r7-minio r7-app; do
  printf "%-14s %s\n" "$name" "$(container_state "$name")"
done
