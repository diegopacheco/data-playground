#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPTS="$ROOT/scripts"
RUN="$ROOT/.run"
CONNECT_IMAGE="docker.io/redpandadata/connect:4.115.1"
REDPANDA_IMAGE="docker.io/redpandadata/redpanda:v26.2.6"
POSTGRES_IMAGE="docker.io/library/postgres:18.6-alpine"
PYTHON_IMAGE="docker.io/library/python:3.14.10-slim"
APP_IMAGE="t5-redpanda-connect-yaml-pipelines:latest"
CONTAINERS="t5-redpanda t5-postgres t5-connect t5-ui"
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
    kafka) printf "kafka://localhost:%s\n" "$(service_port "$1")" ;;
    postgres) printf "postgresql://localhost:%s/orders\n" "$(service_port "$1")" ;;
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
  podman exec t5-redpanda rpk cluster health 2>/dev/null | grep -q 'Healthy:.*true'
}

postgres_ready() {
  podman exec t5-postgres pg_isready -U connect -d orders
}

ensure_topic() {
  if ! podman exec t5-redpanda rpk topic list 2>/dev/null | awk '{print $1}' | grep -qx "$1"; then
    podman exec t5-redpanda rpk topic create "$1" -p "$2" >/dev/null || fail "could not create topic $1"
  fi
}

prepare_out_volume() {
  podman volume exists t5-connect-out || podman volume create t5-connect-out >/dev/null || fail "could not create volume t5-connect-out"
  podman run --rm --user 0 --entrypoint /bin/sh -v t5-connect-out:/out "$CONNECT_IMAGE" -c 'mkdir -p /out/priority && chown 10001:10001 /out/priority' || fail "could not hand t5-connect-out to the connect user"
}

customers_loaded() {
  [ "$(podman exec t5-postgres psql -U connect -d orders -Atc 'SELECT count(*) FROM customers')" -gt 0 ]
}

orders_stream_active() {
  curl -sf -m 3 "$(service_url connect)/connect/streams" | grep -q '"orders":{"active":true'
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
