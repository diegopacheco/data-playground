#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPTS="$ROOT/scripts"
RUN="$ROOT/.run"
MZ_IMAGE="docker.io/materialize/materialized:v26.48.2"
REDPANDA_IMAGE="docker.io/redpandadata/redpanda:v26.2.6"
FLINK_BASE_IMAGE="docker.io/library/flink:2.2.1-java21"
PYTHON_IMAGE="docker.io/library/python:3.14.10-slim"
FLINK_IMAGE="t2-flink:2.2.1-kafka-5.0.0"
APP_IMAGE="t2-materialize-vs-flink-sql:latest"
CONTAINERS="t2-redpanda t2-materialize t2-flink-jm t2-flink-tm t2-flink-gateway t2-app"
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
    mzsql) printf "postgresql://materialize@localhost:%s/materialize\n" "$(service_port "$1")" ;;
    kafka) printf "kafka://localhost:%s\n" "$(service_port "$1")" ;;
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

mz_system() {
  podman exec t2-materialize psql -h localhost -p 6877 -U mz_system -d materialize -v ON_ERROR_STOP=1 -qAt "$@"
}

redpanda_ready() {
  podman exec t2-redpanda rpk cluster health 2>/dev/null | grep -q 'Healthy:.*true'
}

materialize_ready() {
  mz_system -c "SELECT 1" >/dev/null && podman exec t2-materialize psql -h localhost -p 6875 -U materialize -d materialize -qAt -c "SELECT 1" >/dev/null
}

flink_ready() {
  curl -sf -m 3 "$(service_url flinkui)/overview" | grep -q '"taskmanagers":[1-9]' && curl -sf -m 3 "$(service_url gateway)/v1/info" >/dev/null
}

api() {
  curl -sf -m 60 "$(service_url ui)/api/$1"
}

api_post() {
  curl -sf -m 240 -X POST "$(service_url ui)/api/$1"
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
