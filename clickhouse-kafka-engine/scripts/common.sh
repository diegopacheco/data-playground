#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPTS="$ROOT/scripts"
RUN="$ROOT/.run"
LOGS="$RUN/logs"
cd "$ROOT"

mkdir -p "$RUN" "$LOGS"

SERVICES="$(grep '=' "$SCRIPTS/ports.env" || true)"

KAFKA_CONTAINER=i30-kafka
CLICKHOUSE_CONTAINER=i30-clickhouse
KAFKA_BIN=/opt/kafka/bin
KAFKA_INTERNAL=i30-kafka:29092
TOPIC=orders
CSV="$ROOT/data/orders.csv"
PYTHON="${PYTHON:-python3.14}"

log() {
  printf "[%s] %s\n" "$(date +%H:%M:%S)" "$*"
}

fail() {
  printf "ERROR: %s\n" "$*" >&2
  exit 1
}

require() {
  command -v "$1" >/dev/null 2>&1 || fail "$1 is required but not installed"
}

service_names() {
  printf "%s\n" "$SERVICES" | sed '/^$/d' | cut -d= -f1
}

service_port() {
  printf "%s\n" "$SERVICES" | awk -F= -v n="$1" '$1==n{print $2; exit}'
}

service_url() {
  local port
  port="$(service_port "$1")"
  case "$1" in
    kafka) printf "kafka://localhost:%s\n" "$port" ;;
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
  wait_for "${2:-60}" port_up "$1"
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

clickhouse_ready() {
  podman exec "$CLICKHOUSE_CONTAINER" clickhouse-client -q "SELECT 1"
}

ch() {
  podman exec -i "$CLICKHOUSE_CONTAINER" clickhouse-client "$@"
}

topic_size() {
  podman exec "$KAFKA_CONTAINER" "$KAFKA_BIN/kafka-get-offsets.sh" --bootstrap-server "$KAFKA_INTERNAL" --topic "$TOPIC" \
    | awk -F: '{s+=$3} END {print s+0}'
}

csv_rows() {
  awk 'NR>1 && NF>0' "$CSV" | wc -l | tr -d ' '
}

orders_as_json() {
  awk -F, 'NR>1 && NF>=7 {printf "{\"order_id\":%d,\"customer\":\"%s\",\"product\":\"%s\",\"category\":\"%s\",\"quantity\":%d,\"price\":%s,\"ts\":\"%s\"}\n", $1, $2, $3, $4, $5, $6, $7}' "$CSV"
}

produce_orders() {
  orders_as_json | podman exec -i "$KAFKA_CONTAINER" "$KAFKA_BIN/kafka-console-producer.sh" \
    --bootstrap-server "$KAFKA_INTERNAL" --topic "$TOPIC"
}

ingested_orders() {
  ch -q "SELECT count() FROM sales.orders"
}

orders_ingested() {
  [ "$(ingested_orders)" = "$1" ]
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
  if bg_running "$1"; then
    kill "$(cat "$RUN/$1.pid")" 2>/dev/null || true
    log "$1 stopped"
  fi
  rm -f "$RUN/$1.pid"
}

open_url() {
  if command -v open >/dev/null 2>&1; then
    open "$1"
  elif command -v xdg-open >/dev/null 2>&1; then
    xdg-open "$1"
  else
    printf "%s\n" "$1"
  fi
}
