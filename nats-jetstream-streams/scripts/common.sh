#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPTS="$ROOT/scripts"
RUN="$ROOT/.run"
NATS_IMAGE="docker.io/library/nats:2.15.0"
PYTHON_IMAGE="docker.io/library/python:3.14.7-slim"
APP_IMAGE="r8-nats-jetstream-streams:latest"
NODES="r8-nats-1 r8-nats-2 r8-nats-3"
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
    nats*) printf "nats://localhost:%s\n" "$(service_port "$1")" ;;
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

api() {
  curl -sf -m 60 "$(service_url ui)/api/$1"
}

api_post() {
  curl -sf -m 180 -X POST "$(service_url ui)/api/$1"
}

jetstream_ready() {
  local n
  for n in 1 2 3; do
    curl -sf -m 3 "$(service_url "monitor$n")/healthz" >/dev/null || return 1
  done
  python3 -c 'import json,sys,urllib.request
metas=[json.load(urllib.request.urlopen(u+"/jsz",timeout=3)).get("meta_cluster") or {} for u in sys.argv[1:]]
leaders={m.get("leader") for m in metas}
sys.exit(0 if len(leaders)==1 and None not in leaders and all(m.get("cluster_size")==3 for m in metas) else 1)' "$(service_url monitor1)" "$(service_url monitor2)" "$(service_url monitor3)"
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
