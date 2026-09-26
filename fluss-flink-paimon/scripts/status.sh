#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

for name in $(service_names); do
  port="$(service_port "$name")"
  pid="$(port_pid "$port")"
  if [ -n "$pid" ]; then
    printf "%-22s %-6s UP   pid %s\n" "$name" "$port" "$pid"
  else
    printf "%-22s %-6s DOWN\n" "$name" "$port"
  fi
done

for container in $CONTAINERS; do
  state="$(container_state "$container")"
  if [ "$state" = "running" ]; then
    printf "%-22s %-6s UP\n" "$container" "-"
  else
    printf "%-22s %-6s DOWN\n" "$container" "-"
  fi
done
