#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPTS="$ROOT/scripts"
RUN="$ROOT/.run"
AUTOMQ_IMAGE="docker.io/automqinc/automq:1.7.4"
MINIO_IMAGE="docker.io/pgsty/minio:RELEASE.2026-08-04T00-00-00Z"
PYTHON_IMAGE="docker.io/library/python:3.14.7-slim"
APP_IMAGE="r9-automq-diskless-kafka:latest"
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
    controller|broker) printf "kafka://localhost:%s\n" "$(service_port "$1")" ;;
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

api() {
  curl -sf -X "$1" -H "Content-Type: application/json" "$(service_url ui)$2" ${3:+-d "$3"}
}

node_ready() {
  podman logs --since "${3:-2000-01-01T00:00:00Z}" "$1" 2>&1 | grep "\[KafkaRaftServer nodeId=$2\] Kafka Server started" >/dev/null
}

brokers_registered() {
  api GET /api/cluster | python3 -c "import json,sys;c=json.load(sys.stdin);sys.exit(0 if {b['id'] for b in c['brokers']} == {0, 1} else 1)"
}

leaders_assigned() {
  api GET /api/cluster | python3 -c "import json,sys;c=json.load(sys.stdin);t=[x for x in c['topics'] if x['name']=='orders'];sys.exit(0 if t and all(p['leader'] in (0,1) for p in t[0]['partitions']) else 1)"
}

cluster_settled() {
  brokers_registered && leaders_assigned
}

data_ready() {
  [ -s "$ROOT/data/orders.jsonl" ]
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
