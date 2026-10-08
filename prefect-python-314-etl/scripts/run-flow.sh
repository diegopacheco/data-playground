#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

[ -f "$RUN/serve.pid" ] && kill -0 "$(cat "$RUN/serve.pid")" 2>/dev/null || fail "serve process is not running, run ./scripts/start-all.sh first"

out="$("$VENV/bin/prefect" deployment run "$DEPLOYMENT" --watch --watch-timeout 60 2>&1)" || { printf "%s\n" "$out" >&2; fail "flow run failed"; }
printf "%s\n" "$out" | grep -E "UUID|Flow run|finished|state" || true
