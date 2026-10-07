#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

for name in $(service_names); do
  port="$(service_port "$name")"
  pid="$(port_pid "$port")"
  if [ -n "$pid" ]; then
    printf "%-14s %-6s UP   pid %-7s %s\n" "$name" "$port" "$pid" "$(service_url "$name")"
  else
    printf "%-14s %-6s DOWN\n" "$name" "$port"
  fi
done

for container in $CONTAINERS; do
  if [ "$(container_state "$container")" = "running" ]; then
    printf "%-14s %-6s UP\n" "$container" "-"
  else
    printf "%-14s %-6s DOWN\n" "$container" "-"
  fi
done
