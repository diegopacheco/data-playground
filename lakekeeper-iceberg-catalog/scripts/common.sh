#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPTS="$ROOT/scripts"
cd "$ROOT"

LAKEKEEPER_IMAGE="quay.io/lakekeeper/catalog:v0.13.6"
POSTGRES_IMAGE="docker.io/library/postgres:18.6-alpine"
MINIO_IMAGE="docker.io/pgsty/minio:RELEASE.2026-08-04T00-00-00Z"
APP_IMAGE="q4-lakekeeper-iceberg-catalog:latest"
BUCKET="lakehouse"

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
    postgres) printf "postgresql://localhost:%s/lakekeeper\n" "$port" ;;
    *) printf "http://localhost:%s\n" "$port" ;;
  esac
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

mc() {
  podman exec q4-minio mc "$@"
}

pg_ready() {
  podman exec q4-postgres pg_isready -U lakekeeper -d lakekeeper
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
