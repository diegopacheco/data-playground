#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

for name in $(service_names); do
  port_up "$(service_port "$name")" || fail "$name is DOWN, run scripts/start-all.sh first"
  open_url "$(service_url "$name")/#/overview"
done
