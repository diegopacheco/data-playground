#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPTS="$ROOT/scripts"
RUN="$ROOT/.run"
REDPANDA_IMAGE="docker.io/redpandadata/redpanda:v26.2.3"
POSTGRES_IMAGE="docker.io/library/postgres:18.6"
PYTHON_IMAGE="docker.io/library/python:3.14.7-slim"
APP_IMAGE="r13-kappa-vs-lambda-backfill:latest"
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
    redpanda) printf "kafka://localhost:%s\n" "$(service_port "$1")" ;;
    postgres) printf "postgresql://backfill:backfill@localhost:%s/backfill\n" "$(service_port "$1")" ;;
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

redpanda_ready() {
  podman exec r13-redpanda rpk cluster health 2>/dev/null | grep -q 'Healthy:.*true'
}

postgres_ready() {
  podman exec r13-postgres pg_isready -U backfill -d backfill
}

scenario_ready() {
  curl -sf "$(service_url ui)/api/scenario" >/dev/null
}

run_scenario() {
  mkdir -p "$RUN/logs"
  curl -sf -X POST --max-time 300 "$(service_url ui)/api/scenario" >"$RUN/logs/scenario.json" || fail "scenario failed, see: podman logs r13-app"
  grep -q '"generated_at": "[^"]*", "ok": true' "$RUN/logs/scenario.json" || fail "scenario ran but a check failed, see .run/logs/scenario.json"
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
