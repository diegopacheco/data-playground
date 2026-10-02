#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPTS="$ROOT/scripts"
cd "$ROOT"

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
    postgres) printf "postgresql://localhost:%s/crm\n" "$port" ;;
    cassandra) printf "cassandra://localhost:%s\n" "$port" ;;
    rest) printf "http://localhost:%s/v1/config\n" "$port" ;;
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

postgres_ready() {
  podman exec i35-postgres pg_isready -U i35 -d crm
}

cassandra_ready() {
  podman exec i35-cassandra cqlsh -e "DESCRIBE KEYSPACES"
}

minio_ready() {
  curl -sf "$(service_url minio)/minio/health/ready"
}

rest_ready() {
  curl -sf "$(service_url rest)"
}

trino_ready() {
  curl -sf "$(service_url trino)/v1/info" | grep -q '"starting":false'
}

ui_ready() {
  curl -sf "$(service_url ui)/"
}

wait_ready() {
  local name rounds
  name="$1"
  rounds="${2:-1}"
  while [ "$rounds" -gt 0 ]; do
    if wait_until 60 "${name}_ready"; then
      log "$name ready"
      return 0
    fi
    rounds=$((rounds - 1))
  done
  fail "$name not ready"
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
