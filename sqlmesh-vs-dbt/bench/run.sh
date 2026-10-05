#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="$ROOT/.venv/bin/python"
LOGS="$ROOT/.run/logs"
mkdir -p "$LOGS"
cd "$ROOT/bench"
"$PY" sqlmesh_bench.py >"$LOGS/sqlmesh_bench.log" 2>&1 || { tail -20 "$LOGS/sqlmesh_bench.log" >&2; exit 1; }
"$PY" dbt_bench.py >"$LOGS/dbt_bench.log" 2>&1 || { tail -20 "$LOGS/dbt_bench.log" >&2; exit 1; }
"$PY" compare.py
