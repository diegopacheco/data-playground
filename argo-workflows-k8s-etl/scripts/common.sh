#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPTS="$ROOT/scripts"
RUN="$ROOT/.run"
CLUSTER="t8-argo"
CTX="kind-$CLUSTER"
NODE="$CLUSTER-control-plane"
NETWORK="t8-kind"
NODE_MEMORY="2560m"
NAMESPACE="t8-etl"
ARGO_VERSION="v4.1.6"
ARGO_INSTALL="$RUN/argo-install-$ARGO_VERSION.yaml"
APP_IMAGE="localhost/t8-argo-etl:v1"
export KIND_EXPERIMENTAL_PROVIDER=podman
export KIND_EXPERIMENTAL_PODMAN_NETWORK="$NETWORK"
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
    postgres) printf "postgresql://localhost:%s/etl\n" "$(service_port "$1")" ;;
    *) printf "http://localhost:%s\n" "$(service_port "$1")" ;;
  esac
}

render() {
  local args name
  args=""
  for name in $(service_names); do
    args="$args -e s/__${name}__/$(service_port "$name")/g"
  done
  sed $args "$1"
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

http_ok() {
  curl -sf -m 3 -o /dev/null "$1"
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

wait_rollout() {
  local i
  for i in 1 2 3 4 5; do
    if k -n "$1" rollout status deployment "$2" --timeout=60s >/dev/null 2>&1; then return 0; fi
    log "still waiting for $1/$2 ($i/5)"
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
