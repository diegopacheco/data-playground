#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPTS="$ROOT/scripts"
RUN="$ROOT/.run"
CLUSTER="strimzi-kafka-kind-java25"
CTX="kind-$CLUSTER"
NS="kafka"
KAFKA="orders-cluster"
STRIMZI_VERSION="1.3.1"
PRODUCER_IMAGE="localhost/strimzi-order-producer:v1"
CONSUMER_IMAGE="localhost/strimzi-order-consumer:v1"
export KIND_EXPERIMENTAL_PROVIDER=podman
export JAVA_HOME="$HOME/.sdkman/candidates/java/25.0.4-amzn"
export PATH="$JAVA_HOME/bin:$PATH"
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
    producer) printf "http://localhost:%s/runs\n" "$(service_port "$1")" ;;
    *) printf "http://localhost:%s\n" "$(service_port "$1")" ;;
  esac
}

service_target() {
  case "$1" in
    producer) printf "%s\n" "svc/order-producer 8080" ;;
  esac
}

forward_pid() {
  local f
  f="$RUN/$1.pid"
  [ -f "$f" ] && kill -0 "$(cat "$f")" 2>/dev/null && cat "$f" || true
}

k() {
  kubectl --context "$CTX" -n "$NS" "$@"
}

cluster_exists() {
  local clusters
  clusters="$(kind get clusters 2>/dev/null || true)"
  printf "%s\n" "$clusters" | grep -x "$CLUSTER" >/dev/null
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

wait_long() {
  local rounds i
  rounds="$1"
  shift
  for i in $(seq 1 "$rounds"); do
    if wait_until 60 "$@"; then return 0; fi
    log "still waiting ($i/$rounds): $*"
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

resource_ready() {
  [ "$(k get "$1" -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}' 2>/dev/null)" = "True" ]
}

pods_ready() {
  local out
  out="$(k get pods "$@" --no-headers 2>/dev/null)"
  [ -n "$out" ] && ! printf "%s\n" "$out" | awk '{split($2,a,"/"); if (a[1]!=a[2] && $3!="Completed") bad=1} END{exit !bad}'
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
