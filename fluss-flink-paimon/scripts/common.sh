#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPTS="$ROOT/scripts"
RUN="$ROOT/.run"
FLUSS_IMAGE="docker.io/apache/fluss:1.0.0"
ZOOKEEPER_IMAGE="docker.io/library/zookeeper:3.9.5"
JRE_IMAGE="docker.io/library/eclipse-temurin:25.0.4_7-jre"
APP_IMAGE="r1-fluss-flink-paimon:latest"
CONTAINERS="r1-zookeeper r1-fluss-coordinator r1-fluss-tablet r1-app"
SDK_JAVA="$HOME/.sdkman/candidates/java/25.0.4-amzn"
if [ -d "$SDK_JAVA" ]; then
  export JAVA_HOME="$SDK_JAVA"
  export PATH="$JAVA_HOME/bin:$PATH"
fi
cd "$ROOT"

SERVICES="$(grep '=' "$SCRIPTS/ports.env" || true)"

service_names() {
  printf "%s\n" "$SERVICES" | sed '/^$/d' | cut -d= -f1
}

service_port() {
  printf "%s\n" "$SERVICES" | awk -F= -v n="$1" '$1==n{print $2; exit}'
}

service_url() {
  printf "http://localhost:%s\n" "$(service_port "$1")"
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

lake_offset() {
  api status | python3 -c 'import json,sys; s=json.load(sys.stdin)["lakeSnapshot"]; print(sum(o["offset"] for o in s["offsets"]) if s else 0)'
}

lake_ready() {
  [ "$(lake_offset)" -gt 0 ]
}

build_app() {
  require mvn
  java -version 2>&1 | grep -q 'version "25' || fail "java 25 is required to build the app"
  mvn -q -DskipTests package || fail "maven build failed"
  podman build -q -t "$APP_IMAGE" -f "$ROOT/Containerfile" "$ROOT" >/dev/null || fail "image build failed"
  if [ "$(container_state r1-app)" != "absent" ]; then
    podman rm -f r1-app >/dev/null || fail "could not remove the old r1-app container"
  fi
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
