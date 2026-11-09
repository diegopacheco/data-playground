#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPTS="$ROOT/scripts"
RUN="$ROOT/.run"
CLUSTER="cronjob-watermark-microbatch"
CTX="kind-$CLUSTER"
JAVA_IMAGE="localhost/cronjob-watermark-microbatch-java:v1"
PYTHON_IMAGE="localhost/cronjob-watermark-microbatch-python:v1"
POSTGRES_IMAGE="docker.io/library/postgres:18.6-alpine"
DB_NAME="microbatch"
DB_USER="microbatch"
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
    postgres) printf "postgresql://localhost:%s/%s\n" "$(service_port "$1")" "$DB_NAME" ;;
  esac
}

service_target() {
  case "$1" in
    postgres) printf "%s\n" "svc/postgres 5432" ;;
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

psql_exec() {
  k exec -i postgres-0 -- psql -v ON_ERROR_STOP=1 -U "$DB_USER" -d "$DB_NAME" "$@"
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

load_image() {
  local tar
  tar="$RUN/$(printf "%s" "$1" | tr '/:' '__').tar"
  podman save -o "$tar" "$1" || fail "image save failed for $1"
  kind load image-archive "$tar" --name "$CLUSTER" || fail "kind load failed for $1"
  rm -f "$tar"
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
