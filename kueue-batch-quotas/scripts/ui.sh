#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

port_up "$(service_port kueueviz)" || fail "kueueviz is not forwarded, run scripts/start-all.sh first"
log "kueueviz: $(service_url kueueviz)"
if command -v open >/dev/null 2>&1; then open "$(service_url kueueviz)"; fi
