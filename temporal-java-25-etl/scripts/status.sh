#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

down=0
printf "%-12s %-8s %-6s %s\n" SERVICE PORT STATE PID
for name in $(service_names); do
  port="$(service_port "$name")"
  pid="$(port_pid "$port")"
  if [ -n "$pid" ]; then
    printf "%-12s %-8s %-6s %s\n" "$name" "$port" UP "$pid"
  else
    printf "%-12s %-8s %-6s %s\n" "$name" "$port" DOWN "-"
    down=$((down + 1))
  fi
done

pid="$(bg_pid worker)"
if [ -n "$pid" ]; then
  printf "%-12s %-8s %-6s %s\n" worker - UP "$pid"
else
  printf "%-12s %-8s %-6s %s\n" worker - DOWN "-"
  down=$((down + 1))
fi

exit "$down"
