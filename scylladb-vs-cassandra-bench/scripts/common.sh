#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPTS="$ROOT/scripts"
RUN="$ROOT/.run"
LOGS="$RUN/logs"
cd "$ROOT"

mkdir -p "$RUN" "$LOGS"

SERVICES="$(grep -v '^[[:space:]]*#' "$SCRIPTS/ports.env" | grep '=' || true)"

SCYLLA_CONTAINER=i47-scylla
CASSANDRA_CONTAINER=i47-cassandra
RESULTS="$ROOT/results.json"
BENCH_CSV="$ROOT/data/bench-orders.csv"

service_names() {
  printf "%s\n" "$SERVICES" | sed '/^$/d' | cut -d= -f1
}

service_port() {
  printf "%s\n" "$SERVICES" | sed '/^$/d' | awk -F= -v n="$1" '$1==n{print $2; exit}'
}

service_url() {
  local port
  port="$(service_port "$1")"
  case "$1" in
    scylla|cassandra) printf "cql://localhost:%s\n" "$port" ;;
    *) printf "http://localhost:%s\n" "$port" ;;
  esac
}

java_bin() {
  local candidate
  candidate="$(ls -d "$HOME"/.sdkman/candidates/java/25* 2>/dev/null | sort | tail -1 || true)"
  if [ -n "$candidate" ] && [ -x "$candidate/bin/java" ]; then
    printf "%s\n" "$candidate"
  elif [ -n "${JAVA_HOME:-}" ]; then
    printf "%s\n" "$JAVA_HOME"
  else
    fail "Java 25 not found, install it with: sdk install java 25.0.4-amzn"
  fi
}

run_java() {
  "$JAVA_HOME/bin/java" -Xmx512m --enable-native-access=ALL-UNNAMED --sun-misc-unsafe-memory-access=allow -cp "$CLASSPATH_APP" "$@"
}

port_pid() {
  lsof -ti "tcp:$1" -sTCP:LISTEN 2>/dev/null | head -1 || true
}

port_up() {
  [ -n "$(port_pid "$1")" ]
}

wait_port_up() {
  local tries
  tries="${2:-60}"
  while [ "$tries" -gt 0 ]; do
    if port_up "$1"; then return 0; fi
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

wait_for() {
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

cql_ready() {
  podman exec "$1" cqlsh -e "SELECT release_version FROM system.local"
}

bg_running() {
  [ -f "$RUN/$1.pid" ] && kill -0 "$(cat "$RUN/$1.pid")" 2>/dev/null
}

start_bg() {
  local name
  name="$1"
  shift
  if bg_running "$name"; then
    log "$name already running"
    return 0
  fi
  ( cd "$ROOT" && exec "$@" >"$LOGS/$name.log" 2>&1 ) &
  echo $! >"$RUN/$name.pid"
  log "$name started pid $!"
}

stop_bg() {
  local name pid tries
  name="$1"
  if [ -f "$RUN/$name.pid" ]; then
    pid="$(cat "$RUN/$name.pid")"
    if kill -0 "$pid" 2>/dev/null; then
      kill -TERM "$pid" 2>/dev/null || true
      tries=20
      while [ "$tries" -gt 0 ] && kill -0 "$pid" 2>/dev/null; do
        sleep 1
        tries=$((tries - 1))
      done
      kill -KILL "$pid" 2>/dev/null || true
    fi
    rm -f "$RUN/$name.pid"
  fi
  log "$name stopped"
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

JAVA_HOME="$(java_bin)"
export JAVA_HOME
export DB_HOST=localhost
export SCYLLA_PORT="$(service_port scylla)"
export CASSANDRA_PORT="$(service_port cassandra)"
export UI_PORT="$(service_port ui)"
export RESULTS_FILE="$RESULTS"
export BENCH_CSV
export BASE_CSV="$ROOT/data/orders.csv"
CLASSPATH_APP="$ROOT/target/classes:$ROOT/target/lib/*"
