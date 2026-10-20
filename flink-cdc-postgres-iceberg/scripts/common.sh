#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPTS="$ROOT/scripts"
RUN="$ROOT/.run"
LOGS="$RUN/logs"
cd "$ROOT"

mkdir -p "$RUN" "$LOGS"

PG_CONTAINER=i18-postgres
PG_USER=cdc
PG_DB=shop
SDK_JAVA="$HOME/.sdkman/candidates/java/25.0.4-amzn"
if [ -d "$SDK_JAVA" ]; then
  export JAVA_HOME="$SDK_JAVA"
  export PATH="$JAVA_HOME/bin:$PATH"
fi
CLASSPATH_APP="$ROOT/target/classes:$ROOT/target/lib/*"
JAVA_FLAGS="-Xmx512m --sun-misc-unsafe-memory-access=allow --enable-native-access=ALL-UNNAMED --add-opens=java.base/java.lang=ALL-UNNAMED --add-opens=java.base/java.util=ALL-UNNAMED --add-opens=java.base/java.nio=ALL-UNNAMED --add-opens=java.base/sun.nio.ch=ALL-UNNAMED -Dorg.slf4j.simpleLogger.defaultLogLevel=warn -Dorg.slf4j.simpleLogger.log.org.apache.flink.streaming.api.operators.collect=error"

SERVICES=""
if [ -f "$SCRIPTS/ports.env" ]; then
  SERVICES="$(grep -v '^[[:space:]]*#' "$SCRIPTS/ports.env" | grep '=' || true)"
fi

service_names() {
  printf "%s\n" "$SERVICES" | sed '/^$/d' | cut -d= -f1 | grep -v '^flink_'
}

service_port() {
  printf "%s\n" "$SERVICES" | sed '/^$/d' | awk -F= -v n="$1" '$1==n{print $2; exit}'
}

export APP_ROOT="$ROOT"
export PG_PORT="$(service_port postgres)"
export UI_PORT="$(service_port ui)"
export FLINK_PIPELINE_BLOB_PORT="$(service_port flink_pipeline_blob)"
export FLINK_PIPELINE_DATA_PORT="$(service_port flink_pipeline_data)"
export FLINK_PIPELINE_REST_PORT="$(service_port flink)"
export FLINK_READER_BLOB_PORT="$(service_port flink_reader_blob)"
export FLINK_READER_DATA_PORT="$(service_port flink_reader_data)"
export FLINK_READER_REST_PORT="$(service_port flink_reader_rest)"

service_url() {
  local port
  port="$(service_port "$1")"
  case "$1" in
    postgres) printf "postgresql://localhost:%s/%s\n" "$port" "$PG_DB" ;;
    *) printf "http://localhost:%s\n" "$port" ;;
  esac
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

psql_run() {
  podman exec -i "$PG_CONTAINER" psql -U "$PG_USER" -d "$PG_DB" -v ON_ERROR_STOP=1 -q "$@"
}

pg_ready() {
  psql_run -tAc "SELECT count(*) FROM orders" >/dev/null 2>&1
}

wait_pg_ready() {
  local tries
  tries="${1:-60}"
  while [ "$tries" -gt 0 ]; do
    if pg_ready; then return 0; fi
    sleep 1
    tries=$((tries - 1))
  done
  return 1
}

pid_alive() {
  [ -f "$RUN/$1.pid" ] && kill -0 "$(cat "$RUN/$1.pid")" 2>/dev/null
}

start_bg() {
  local name
  name="$1"
  shift
  if pid_alive "$name"; then
    log "$name already running"
    return 0
  fi
  ( exec "$@" >"$LOGS/$name.log" 2>&1 ) &
  echo $! >"$RUN/$name.pid"
  log "$name started pid $!"
}

stop_bg() {
  local name pid port
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
  port="$(service_port "$name" || true)"
  if [ -n "$port" ]; then
    wait_port_down "$port" 10 || true
    pid="$(port_pid "$port")"
    if [ -n "$pid" ]; then kill -KILL "$pid" 2>/dev/null || true; fi
  fi
  log "$name stopped"
}

compare_json() {
  curl -fsS "$(service_url ui)/api/compare"
}

in_sync() {
  compare_json 2>/dev/null | python3 -c 'import json,sys; d=json.load(sys.stdin); sys.exit(0 if d.get("in_sync") else 1)' 2>/dev/null
}

wait_in_sync() {
  local deadline
  deadline=$(( $(date +%s) + ${1:-60} ))
  while [ "$(date +%s)" -lt "$deadline" ]; do
    if in_sync; then return 0; fi
    sleep 1
  done
  return 1
}

build_app() {
  require mvn
  mvn -q -DskipTests clean package || fail "maven build failed"
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
