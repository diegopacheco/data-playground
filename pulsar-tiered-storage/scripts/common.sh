#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPTS="$ROOT/scripts"
RUN="$ROOT/.run"
PULSAR_IMAGE="docker.io/apachepulsar/pulsar:4.2.4"
MINIO_IMAGE="docker.io/pgsty/minio:RELEASE.2026-08-04T00-00-00Z"
MC_IMAGE="docker.io/pgsty/mc:RELEASE.2026-09-16T00-00-00Z"
PYTHON_IMAGE="docker.io/library/python:3.14.7-slim"
BROKER_IMAGE="r7-pulsar-offloaders:4.2.4"
APP_IMAGE="r7-pulsar-tiered-storage:latest"
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
    broker) printf "http://localhost:%s/admin/v2\n" "$(service_port "$1")" ;;
    bookie) printf "http://localhost:%s/api/v1\n" "$(service_port "$1")" ;;
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

container_exit() {
  podman inspect -f '{{.State.ExitCode}}' "$1" 2>/dev/null || echo "absent"
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

exited_ok() {
  [ "$(container_state "$1")" = "exited" ] && [ "$(container_exit "$1")" = "0" ]
}

zookeeper_ready() {
  podman exec r7-zookeeper bin/pulsar-zookeeper-ruok.sh >/dev/null 2>&1
}

bookie_ready() {
  curl -sf -m 2 "$(service_url bookie)/bookie/state" | grep -q '"running" : true'
}

broker_ready() {
  curl -sf -m 2 "$(service_url broker)/brokers/health" | grep -q ok
}

api() {
  curl -sf -m 120 "$(service_url ui)/api/$1"
}

api_post() {
  curl -sf -m 120 -X POST "$(service_url ui)/api/$1"
}

json_field() {
  python3 -c 'import json,sys; v=json.load(sys.stdin)
for k in sys.argv[1].split("."): v=v[k] if v is not None else None
print(v)' "$1"
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
