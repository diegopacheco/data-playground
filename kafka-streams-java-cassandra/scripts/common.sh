#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPTS="$ROOT/scripts"
RUN="$ROOT/.run"
LOGS="$RUN/logs"
cd "$ROOT"

mkdir -p "$RUN" "$LOGS"

SERVICES="$(grep -v '^[[:space:]]*#' "$SCRIPTS/ports.env" | grep '=' || true)"

KAFKA_CONTAINER=p3-kafka
CASSANDRA_CONTAINER=p3-cassandra
KAFKA_BIN=/opt/kafka/bin
KAFKA_INTERNAL=localhost:29092
TOPIC=orders

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
    kafka) printf "kafka://localhost:%s\n" "$port" ;;
    cassandra) printf "cql://localhost:%s\n" "$port" ;;
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
  "$JAVA_HOME/bin/java" -Xmx256m -cp "$CLASSPATH_APP" "$@"
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

kafka_ready() {
  podman exec "$KAFKA_CONTAINER" "$KAFKA_BIN/kafka-topics.sh" --bootstrap-server "$KAFKA_INTERNAL" --list
}

cassandra_ready() {
  podman exec "$CASSANDRA_CONTAINER" cqlsh -e "DESCRIBE KEYSPACES"
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
export KAFKA_BOOTSTRAP="localhost:$(service_port kafka)"
export CASSANDRA_HOST=localhost
export CASSANDRA_PORT="$(service_port cassandra)"
export UI_PORT="$(service_port ui)"
export STREAMS_STATE_DIR="$RUN/kafka-streams"
CLASSPATH_APP="$ROOT/target/classes:$ROOT/target/lib/*"
