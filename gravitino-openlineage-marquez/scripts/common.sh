#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPTS="$ROOT/scripts"
RUN="$ROOT/.run"
cd "$ROOT"

GRAVITINO_IMAGE="docker.io/apache/gravitino:1.3.0"
MARQUEZ_IMAGE="docker.io/marquezproject/marquez:0.51.1"
MARQUEZ_WEB_IMAGE="docker.io/marquezproject/marquez-web:0.51.1"
POSTGRES_IMAGE="docker.io/library/postgres:18.6-alpine"
PYTHON_IMAGE="docker.io/library/python:3.14.7-slim"
APP_IMAGE="r6-gravitino-openlineage-marquez:latest"
METALAKE="shop_lake"
JOB_NAMESPACE="shop_pipeline"

SERVICES="$(grep '=' "$SCRIPTS/ports.env" || true)"

service_names() {
  printf "%s\n" "$SERVICES" | sed '/^$/d' | cut -d= -f1
}

service_port() {
  printf "%s\n" "$SERVICES" | awk -F= -v n="$1" '$1==n{print $2; exit}'
}

service_url() {
  local port
  port="$(service_port "$1")"
  case "$1" in
    postgres) printf "postgresql://shop@localhost:%s/shop\n" "$port" ;;
    *) printf "http://localhost:%s\n" "$port" ;;
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

wait_long() {
  local rounds
  rounds="$1"
  shift
  while [ "$rounds" -gt 0 ]; do
    if wait_until 60 "$@"; then return 0; fi
    rounds=$((rounds - 1))
    [ "$rounds" -gt 0 ] && log "  still waiting for: $*"
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

pg_ready() {
  podman exec r6-postgres pg_isready -U shop -d shop
}

psql_value() {
  podman exec r6-postgres psql -U shop -d shop -tAc "$1"
}

gold_rows() {
  psql_value "select count(*) from gold.revenue_by_category" 2>/dev/null || echo 0
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
