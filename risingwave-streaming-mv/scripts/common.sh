#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPTS="$ROOT/scripts"
RUN="$ROOT/.run"
RISINGWAVE_IMAGE="docker.io/risingwavelabs/risingwave:v3.1.0"
REDPANDA_IMAGE="docker.io/redpandadata/redpanda:v26.2.6"
PYTHON_IMAGE="docker.io/library/python:3.15.2-slim"
PSQL_IMAGE="docker.io/library/postgres:18.6-alpine"
APP_IMAGE="t1-risingwave-streaming-mv:latest"
cd "$ROOT"

SERVICES="$(grep '=' "$SCRIPTS/ports.env" || true)"

service_names() {
  printf "%s\n" "$SERVICES" | sed '/^$/d' | cut -d= -f1
}

service_port() {
  printf "%s\n" "$SERVICES" | awk -F= -v n="$1" '$1==n{print $2; exit}'
}

service_url() {
  case "$1" in
    risingwave) printf "postgresql://root@localhost:%s/dev\n" "$(service_port "$1")" ;;
    *) printf "http://localhost:%s\n" "$(service_port "$1")" ;;
  esac
}

port_pid() {
  lsof -ti "tcp:$1" -sTCP:LISTEN 2>/dev/null | head -1 || true
}

port_up() {
  [ -n "$(port_pid "$1")" ]
}

container_state() {
  podman inspect -f '{{.State.Status}}' "$1" 2>/dev/null || echo "absent"
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

compose() {
  podman-compose --env-file "$SCRIPTS/ports.env" -f "$ROOT/podman-compose.yml" "$@"
}

redpanda_ready() {
  curl -sf -m 3 "$(service_url admin)/v1/status/ready" | grep -q ready
}

risingwave_ready() {
  podman exec t1-app python -c 'import os,psycopg; psycopg.connect(os.environ["RW_DSN"]).execute("SELECT 1")'
}

api() {
  curl -sf -m 60 "$(service_url ui)/api/$1"
}

api_post() {
  curl -sf -m 180 -X POST "$(service_url ui)/api/$1"
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
