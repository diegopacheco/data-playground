#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

for name in $(service_names); do
  port="$(service_port "$name")"
  if port_up "$port"; then
    printf "%-6s %-6s UP    pid=%s container=%s\n" "$name" "$port" "$(port_pid "$port")" "$(container_state "i8-$name")"
  else
    printf "%-6s %-6s DOWN  container=%s\n" "$name" "$port" "$(container_state "i8-$name")"
  fi
done
