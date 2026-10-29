#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPTS="$ROOT/scripts"
RUN="$ROOT/.run"
LOGS="$RUN/logs"
cd "$ROOT"

mkdir -p "$RUN" "$LOGS"

KESTRA_IMAGE=docker.io/kestra/kestra:v2.0.3-slim
KESTRA_PLUGINS="io.kestra.plugin:plugin-jdbc-postgres:2.0.4 io.kestra.plugin:plugin-jdbc-duckdb:2.0.4"
KESTRA_AUTH=admin@kestra.io:Kestra2026
NAMESPACE=i40.sales
PIPELINE_FLOW=revenue_pipeline
QUALITY_FLOW=revenue_quality
POSTGRES_CONTAINER=i40-postgres

SERVICES=""
if [ -f "$SCRIPTS/ports.env" ]; then
  SERVICES="$(grep -v '^[[:space:]]*#' "$SCRIPTS/ports.env" | grep '=' || true)"
fi

service_names() {
  printf "%s\n" "$SERVICES" | sed '/^$/d' | cut -d= -f1
}

service_port() {
  printf "%s\n" "$SERVICES" | sed '/^$/d' | awk -F= -v n="$1" '$1==n{print $2; exit}'
}

service_url() {
  local port
  port="$(service_port "$1")"
  case "$1" in
    postgres) printf "postgresql://localhost:%s/sales\n" "$port" ;;
    *) printf "http://localhost:%s\n" "$port" ;;
  esac
}

kestra_api() {
  printf "%s/api/v1/main\n" "$(service_url kestra)"
}

kcurl() {
  curl -sS -u "$KESTRA_AUTH" "$@"
}

json_field() {
  python3 -c '
import json, sys
d = json.load(sys.stdin)
for k in sys.argv[1:]:
    d = d[k]
print(d)
' "$@"
}

execution_state() {
  kcurl "$(kestra_api)/executions/$1" | json_field state current
}

wait_final_state() {
  local tries state
  tries=60
  state=""
  while [ "$tries" -gt 0 ]; do
    state="$(execution_state "$1")"
    case "$state" in
      SUCCESS|FAILED|KILLED|CANCELLED|WARNING) printf "%s\n" "$state"; return 0 ;;
    esac
    sleep 1
    tries=$((tries - 1))
  done
  printf "TIMEOUT_%s\n" "${state:-UNKNOWN}"
}

port_pid() {
  lsof -ti "tcp:$1" -sTCP:LISTEN 2>/dev/null | head -1 || true
}

port_up() {
  [ -n "$(port_pid "$1")" ]
}

wait_port_down() {
  local tries
  tries="${2:-30}"
  while [ "$tries" -gt 0 ]; do
    if ! port_up "$1"; then return 0; fi
    sleep 1
    tries=$((tries - 1))
  done
  return 1
}

wait_cmd() {
  local tries
  tries="$1"
  shift
  while [ "$tries" -gt 0 ]; do
    if "$@" >/dev/null 2>&1; then return 0; fi
    sleep 1
    tries=$((tries - 1))
  done
  return 1
}

postgres_ready() {
  podman exec "$POSTGRES_CONTAINER" pg_isready -U sales -d sales
}

kestra_ready() {
  kcurl -f -o /dev/null "$(service_url kestra)/api/v1/configs"
}

http_ok() {
  curl -sf -o /dev/null "$1"
}

open_url() {
  if command -v open >/dev/null 2>&1; then
    open "$1"
  elif command -v xdg-open >/dev/null 2>&1; then
    xdg-open "$1"
  else
    fail "no browser opener found, open $1 manually"
  fi
}

require() {
  command -v "$1" >/dev/null 2>&1 || fail "$1 is required but not installed"
}

log() {
  printf "%s\n" "$*"
}

fail() {
  printf "ERROR: %s\n" "$*" >&2
  exit 1
}
