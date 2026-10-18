#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPTS="$ROOT/scripts"
RUN="$ROOT/.run"
LOGS="$RUN/logs"
cd "$ROOT"

SERVICES="$(grep '=' "$SCRIPTS/ports.env" || true)"

KAFKA_CONTAINER=s2-kafka
KAFKA_BIN=/opt/kafka/bin
KAFKA_INTERNAL=localhost:29092
BATCH=100
KILL_OFFSETS="337 652"
FENCE_OFFSET=437
JAVA=(java -Xmx128m -cp "$ROOT/target/classes:$ROOT/target/lib/*")

service_names() {
  printf "%s\n" "$SERVICES" | sed '/^$/d' | cut -d= -f1
}

service_port() {
  printf "%s\n" "$SERVICES" | awk -F= -v n="$1" '$1==n{print $2; exit}'
}

service_url() {
  case "$1" in
    kafka) printf "kafka://localhost:%s\n" "$(service_port "$1")" ;;
    *) printf "http://localhost:%s\n" "$(service_port "$1")" ;;
  esac
}

port_pid() {
  lsof -ti "tcp:$1" -sTCP:LISTEN 2>/dev/null | head -1 || true
}

port_up() {
  [ -n "$(port_pid "$1")" ]
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

compose() {
  podman-compose --env-file "$SCRIPTS/ports.env" -f "$ROOT/podman-compose.yml" "$@"
}

kafka_tool() {
  local tool
  tool="$1"
  shift
  podman exec "$KAFKA_CONTAINER" "$KAFKA_BIN/$tool" --bootstrap-server "$KAFKA_INTERNAL" "$@"
}

kafka_ready() {
  kafka_tool kafka-topics.sh --list
}

dump_topic() {
  kafka_tool kafka-console-consumer.sh --topic "$1" --from-beginning --isolation-level "$2" \
    --timeout-ms 3000 --formatter-property print.key=true --formatter-property key.separator=, 2>/dev/null || true
}

event() {
  printf "%s\t%s\t%s\n" "$(($(date +%s) * 1000))" "$1" "$2" >>"$RUN/events.tsv"
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

export KAFKA_BOOTSTRAP="localhost:$(service_port kafka)"
export UI_PORT="$(service_port ui)"
export RUN_DIR="$RUN"
export DATA_FILE="$ROOT/data/payments.csv"
export BATCH
