#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

down=0
printf "%-14s %-8s %-6s %s\n" SERVICE PORT STATE PID
for name in $(service_names); do
  port="$(service_port "$name")"
  pid="$(port_pid "$port")"
  if [ -n "$pid" ]; then
    printf "%-14s %-8s %-6s %s\n" "$name" "$port" UP "$pid"
  else
    printf "%-14s %-8s %-6s %s\n" "$name" "$port" DOWN "-"
    down=$((down + 1))
  fi
done

if [ -f "$RUN/serve.pid" ] && kill -0 "$(cat "$RUN/serve.pid")" 2>/dev/null; then
  printf "%-14s %-8s %-6s %s\n" serve - UP "$(cat "$RUN/serve.pid")"
else
  printf "%-14s %-8s %-6s %s\n" serve - DOWN "-"
  down=$((down + 1))
fi

exit "$down"
