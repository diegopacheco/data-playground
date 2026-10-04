#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPTS="$ROOT/scripts"
RUN="$ROOT/.run"
LOGS="$RUN/logs"
cd "$ROOT"

mkdir -p "$RUN" "$LOGS"

TEMPORAL_CONTAINER=i41-temporal
POSTGRES_CONTAINER=i41-postgres
SDK_JAVA="$HOME/.sdkman/candidates/java/25.0.4-amzn"
if [ -d "$SDK_JAVA" ]; then
  export JAVA_HOME="$SDK_JAVA"
  export PATH="$JAVA_HOME/bin:$PATH"
fi
CLASSPATH_APP="$ROOT/target/classes:$ROOT/target/lib/*"
PKG=com.github.diegopacheco.temporaletl
ORDERS_CSV="data/orders.csv"

SERVICES=""
if [ -f "$SCRIPTS/ports.env" ]; then
  SERVICES="$(grep -v '^[[:space:]]*#' "$SCRIPTS/ports.env" | grep '=' || true)"
fi

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
    postgres) printf "postgresql://localhost:%s/etl\n" "$port" ;;
    temporal) printf "grpc://localhost:%s\n" "$port" ;;
    *) printf "http://localhost:%s\n" "$port" ;;
  esac
}

export TEMPORAL_ADDRESS="localhost:$(service_port temporal)"
export TEMPORAL_UI_URL="$(service_url temporal-ui)"
export PG_URL="jdbc:postgresql://localhost:$(service_port postgres)/etl"
export PG_USER=etl
export PG_PASSWORD=etl
export UI_PORT="$(service_port ui)"

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

pg_ready() {
  podman exec "$POSTGRES_CONTAINER" pg_isready -U etl -d etl
}

temporal_ready() {
  podman exec "$TEMPORAL_CONTAINER" temporal operator namespace describe --namespace default --address 127.0.0.1:7233
}

psql_exec() {
  podman exec -i "$POSTGRES_CONTAINER" psql -U etl -d etl "$@"
}

bg_pid() {
  if [ -f "$RUN/$1.pid" ] && kill -0 "$(cat "$RUN/$1.pid")" 2>/dev/null; then
    cat "$RUN/$1.pid"
  fi
}

start_bg() {
  local name
  name="$1"
  shift
  if [ -n "$(bg_pid "$name")" ]; then
    log "$name already running"
    return 0
  fi
  ( cd "$ROOT" && exec "$@" >"$LOGS/$name.log" 2>&1 ) &
  echo $! >"$RUN/$name.pid"
  log "$name started pid $!"
}

stop_bg() {
  local name pid port
  name="$1"
  pid="$(bg_pid "$name")"
  if [ -n "$pid" ]; then
    kill -TERM "$pid" 2>/dev/null || true
    wait_until 10 sh -c "! kill -0 $pid" || kill -KILL "$pid" 2>/dev/null || true
  fi
  rm -f "$RUN/$name.pid"
  port="$(service_port "$name" || true)"
  if [ -n "$port" ]; then
    wait_port_down "$port" 10 || true
    pid="$(port_pid "$port")"
    if [ -n "$pid" ]; then kill -KILL "$pid" 2>/dev/null || true; fi
  fi
  log "$name stopped"
}

build_app() {
  require mvn
  log "building with maven"
  mvn -q -B package -DskipTests -f "$ROOT/pom.xml" || fail "maven build failed"
}

java_run() {
  java -Xmx256m --sun-misc-unsafe-memory-access=allow -cp "$CLASSPATH_APP" "$@"
}

start_worker() {
  start_bg worker java -Xmx256m --sun-misc-unsafe-memory-access=allow -cp "$CLASSPATH_APP" "$PKG.WorkerMain"
  wait_until 60 grep -q "worker started" "$LOGS/worker.log" || fail "worker did not start, see $LOGS/worker.log"
  log "worker ready: $(grep "worker started" "$LOGS/worker.log" | tail -1)"
}

starter() {
  java_run "$PKG.Starter" "$@"
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
