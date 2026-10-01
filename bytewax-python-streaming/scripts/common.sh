#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPTS="$ROOT/scripts"
RUN="$ROOT/.run"
LOGS="$RUN/logs"
STATE="$ROOT/state"
RECOVERY="$STATE/recovery"
FLOW_PY="$ROOT/.venv/bin/python"
FLOW_PYTHON_VERSION="3.12"
REDPANDA_CONTAINER="i28-redpanda"
CSV="$ROOT/data/orders.csv"
cd "$ROOT"

mkdir -p "$RUN" "$LOGS"

SERVICES=""
if [ -f "$SCRIPTS/ports.env" ]; then
  SERVICES="$(grep -v '^[[:space:]]*#' "$SCRIPTS/ports.env" | grep '=' || true)"
fi

export IN_TOPIC="orders"
export OUT_TOPIC="order-aggregates"
export STORE_DB="$STATE/store.db"
export KAFKA_BROKERS="localhost:$(printf "%s\n" "$SERVICES" | awk -F= '$1=="redpanda"{print $2}')"
export UI_PORT="$(printf "%s\n" "$SERVICES" | awk -F= '$1=="ui"{print $2}')"

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
    redpanda) printf "kafka://localhost:%s\n" "$port" ;;
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

rpk() {
  podman exec -i "$REDPANDA_CONTAINER" rpk "$@"
}

redpanda_ready() {
  rpk cluster info >/dev/null
}

relax_disk_limit() {
  rpk cluster config set storage_min_free_bytes 268435456 >/dev/null
}

topic_exists() {
  rpk topic list | awk 'NR>1{print $1}' | grep -x "$1" >/dev/null
}

ensure_topics() {
  local t
  for t in "$IN_TOPIC" "$OUT_TOPIC"; do
    topic_exists "$t" || rpk topic create "$t" -p 1 >/dev/null || fail "could not create topic $t"
  done
}

recreate_topics() {
  local t
  for t in "$IN_TOPIC" "$OUT_TOPIC"; do
    if topic_exists "$t"; then rpk topic delete "$t" >/dev/null; fi
  done
  wait_for 30 ensure_topics || fail "could not recreate topics"
}

topic_size() {
  rpk topic describe "$1" -p | awk 'NR>1{s+=$NF} END{print s+0}'
}

produce_rows() {
  python3 "$ROOT/dataflow/csv_to_json.py" "$CSV" "$1" "$2" | rpk topic produce "$IN_TOPIC" >>"$LOGS/produce.log" || fail "produce failed"
  log "produced rows $1-$2 of $(basename "$CSV") into topic $IN_TOPIC"
}

init_recovery() {
  if [ ! -d "$RECOVERY" ]; then
    mkdir -p "$RECOVERY"
    "$FLOW_PY" -m bytewax.recovery "$RECOVERY" 1 || fail "could not init recovery partitions"
    log "recovery partitions initialised in state/recovery"
  fi
}

reset_state() {
  rm -rf "$STATE"
  mkdir -p "$STATE"
  init_recovery
}

store_orders() {
  python3 -c 'import sqlite3,sys
try:
    print(sqlite3.connect(sys.argv[1]).execute("SELECT COALESCE(SUM(orders),0) FROM totals").fetchone()[0])
except Exception:
    print(0)' "$STORE_DB"
}

store_has() {
  [ "$(store_orders)" = "$1" ]
}

start_dataflow() {
  mkdir -p "$STATE"
  init_recovery
  start_bg dataflow "$ROOT/dataflow" "$FLOW_PY" -u -m bytewax.run flow:flow -r "$RECOVERY" -s 1 -b 0
}

stop_dataflow() {
  local pid signal
  signal="${1:-TERM}"
  if [ -f "$RUN/dataflow.pid" ]; then
    pid="$(cat "$RUN/dataflow.pid")"
    if kill -0 "$pid" 2>/dev/null; then
      kill "-$signal" "$pid" 2>/dev/null || true
      wait_for 10 pid_gone "$pid" || kill -KILL "$pid" 2>/dev/null || true
    fi
    rm -f "$RUN/dataflow.pid"
  fi
  log "dataflow stopped with SIG$signal"
}

pause_seconds() {
  local n
  n="$1"
  while [ "$n" -gt 0 ]; do
    sleep 1
    n=$((n - 1))
  done
}

pid_gone() {
  ! kill -0 "$1" 2>/dev/null
}

dataflow_pid() {
  if [ -f "$RUN/dataflow.pid" ] && kill -0 "$(cat "$RUN/dataflow.pid")" 2>/dev/null; then
    cat "$RUN/dataflow.pid"
  fi
}

start_bg() {
  local name dir
  name="$1"
  dir="$2"
  shift 2
  if [ -f "$RUN/$name.pid" ] && kill -0 "$(cat "$RUN/$name.pid")" 2>/dev/null; then
    log "$name already running"
    return 0
  fi
  ( cd "$dir" && exec "$@" >>"$LOGS/$name.log" 2>&1 ) &
  echo $! >"$RUN/$name.pid"
  disown
  log "$name started pid $!"
}

stop_bg() {
  local name pid port
  name="$1"
  if [ -f "$RUN/$name.pid" ]; then
    pid="$(cat "$RUN/$name.pid")"
    if kill -0 "$pid" 2>/dev/null; then
      kill -TERM "$pid" 2>/dev/null || true
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
