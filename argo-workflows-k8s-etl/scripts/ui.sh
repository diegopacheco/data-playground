#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

for name in etl_ui argo_ui; do
  port_up "$(service_port "$name")" || fail "$name is DOWN, run scripts/start-all.sh first"
done
open_url "$(service_url etl_ui)"
open_url "$(service_url argo_ui)/workflows/$NAMESPACE"
