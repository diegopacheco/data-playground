#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPTS="$ROOT/scripts"
RUN="$ROOT/.run"
LOGS="$RUN/logs"
cd "$ROOT"

mkdir -p "$RUN" "$LOGS"

REDPANDA_CONTAINER="q1-redpanda"
SOURCE_TOPIC="orders"
RESULT_TOPIC="revenue_by_category"
PIPELINE_NAME="revenue_by_category"

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
    redpanda) printf "kafka://localhost:%s\n" "$port" ;;
    *) printf "http://localhost:%s\n" "$port" ;;
  esac
}

port_pid() {
  lsof -ti "tcp:$1" -sTCP:LISTEN 2>/dev/null | head -1 || true
}

port_up() {
  [ -n "$(port_pid "$1")" ]
}

wait_port_up() {
  local tries
  tries="${2:-60}"
  while [ "$tries" -gt 0 ]; do
    if port_up "$1"; then return 0; fi
    sleep 1
    tries=$((tries - 1))
  done
  return 1
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

wait_until() {
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

compose() {
  podman-compose --env-file "$SCRIPTS/ports.env" -f "$ROOT/podman-compose.yml" "$@"
}

redpanda_ready() {
  podman exec "$REDPANDA_CONTAINER" rpk cluster health | grep -q "Healthy:.*true"
}

produce_orders() {
  tail -n +2 "$ROOT/data/orders.csv" \
    | awk -F, '{printf "{\"order_id\":%s,\"customer\":\"%s\",\"product\":\"%s\",\"category\":\"%s\",\"quantity\":%s,\"price\":%s,\"ts\":\"%s\"}\n",$1,$2,$3,$4,$5,$6,$7}' \
    | podman exec -i "$REDPANDA_CONTAINER" rpk topic produce "$SOURCE_TOPIC"
}

arroyo_api() {
  local method path
  method="$1"
  path="$2"
  shift 2
  curl -sf -X "$method" -H "Content-Type: application/json" "$@" "$(service_url arroyo)/api/v1$path"
}

arroyo_ready() {
  arroyo_api GET /ping
}

json_get() {
  python3 -c "import json,sys
d=json.load(sys.stdin)
$1"
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
