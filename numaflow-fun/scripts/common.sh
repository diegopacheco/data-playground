#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPTS="$ROOT/scripts"
RUN="$ROOT/.run"
CLUSTER="numaflow-fun"
CTX="kind-$CLUSTER"
NUMAFLOW_VERSION="v1.8.4"
IMAGE="localhost/numaflow-fun-udf:v1"
PIPELINE="orders"
export KIND_EXPERIMENTAL_PROVIDER=podman
cd "$ROOT"
mkdir -p "$RUN/logs"

SERVICES="$(grep '=' "$SCRIPTS/ports.env" || true)"

service_names() {
  printf "%s\n" "$SERVICES" | sed '/^$/d' | cut -d= -f1
}

service_port() {
  printf "%s\n" "$SERVICES" | awk -F= -v n="$1" '$1==n{print $2; exit}'
}

service_url() {
  case "$1" in
    orders_in) printf "https://localhost:%s/vertices/in\n" "$(service_port "$1")" ;;
    *) printf "https://localhost:%s\n" "$(service_port "$1")" ;;
  esac
}

service_target() {
  case "$1" in
    ui) printf "%s\n" "-n numaflow-system svc/numaflow-server" ;;
    orders_in) printf "%s\n" "svc/$PIPELINE-in" ;;
  esac
}

forward_pid() {
  local f
  f="$RUN/$1.pid"
  [ -f "$f" ] && kill -0 "$(cat "$f")" 2>/dev/null && cat "$f" || true
}

k() {
  kubectl --context "$CTX" "$@"
}

cluster_exists() {
  kind get clusters 2>/dev/null | grep -qx "$CLUSTER"
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

pods_ready() {
  local out
  out="$(k "$@" get pods --no-headers 2>/dev/null)"
  [ -n "$out" ] && ! printf "%s\n" "$out" | awk '{split($2,a,"/"); if (a[1]!=a[2] && $3!="Completed") bad=1} END{exit !bad}'
}

wait_pods() {
  local i
  for i in 1 2 3 4 5; do
    if wait_until 60 pods_ready "$@"; then return 0; fi
    log "still waiting for pods ($i/5)"
  done
  return 1
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
