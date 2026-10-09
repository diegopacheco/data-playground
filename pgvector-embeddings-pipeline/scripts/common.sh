#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPTS="$ROOT/scripts"
RUN="$ROOT/.run"
PY="$ROOT/.venv/bin/python"
IMAGE="docker.io/pgvector/pgvector:0.8.6-pg18-trixie"
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
    postgres) printf "postgresql://catalog:catalog@localhost:%s/catalog\n" "$(service_port postgres)" ;;
    *) printf "http://localhost:%s\n" "$(service_port "$1")" ;;
  esac
}

port_pid() {
  lsof -ti "tcp:$1" -sTCP:LISTEN 2>/dev/null | head -1 || true
}

port_up() {
  [ -n "$(port_pid "$1")" ]
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

psql_exec() {
  podman exec i48-postgres psql -U catalog -d catalog "$@"
}

run_py() {
  (cd "$ROOT/app" && PGPORT="$(service_port postgres)" UI_PORT="$(service_port ui)" "$PY" "$@")
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
