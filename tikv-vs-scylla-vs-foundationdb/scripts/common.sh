#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPTS="$ROOT/scripts"
RUN="$ROOT/.run"
LOGS="$RUN/logs"
cd "$ROOT"

mkdir -p "$RUN" "$LOGS"

SERVICES="$(grep '=' "$SCRIPTS/ports.env" || true)"

IMAGE=localhost/s6-bench:1.0.0
TIKV_IMAGE=localhost/s6-tikv:v8.5.8
STORES="tikv scylladb foundationdb"
ROWS=200000
DATASET="$ROOT/data/dataset.csv"
RESULTS="$ROOT/results.json"

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
    pd) printf "http://localhost:%s/pd/api/v1/stores\n" "$port" ;;
    tikv) printf "http://localhost:%s/status\n" "$port" ;;
    scylla) printf "cql://localhost:%s\n" "$port" ;;
    foundationdb) printf "fdb://localhost:%s\n" "$port" ;;
    *) printf "http://localhost:%s\n" "$port" ;;
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

container_of() {
  case "$1" in
    scylladb) printf "s6-scylla\n" ;;
    *) printf "s6-%s\n" "$1" ;;
  esac
}

limits() {
  podman inspect "$(container_of "$1")" --format 'memory_bytes={{.HostConfig.Memory}} nano_cpus={{.HostConfig.NanoCpus}}'
}

tikv_ready() {
  curl -sf "$(service_url pd)" | grep -q '"state_name": "Up"'
}

cql() {
  podman exec s6-scylla cqlsh -e "$1"
}

scylla_ready() {
  cql "SELECT version FROM system.versions"
}

fdbcli() {
  podman exec s6-foundationdb fdbcli --timeout 5 --exec "$1"
}

foundationdb_ready() {
  if fdbcli "status minimal" | grep -q "is available"; then return 0; fi
  fdbcli "configure new single ssd" || true
  return 1
}

run_bench() {
  podman rm -f s6-bench >/dev/null 2>&1 || true
  podman run --rm --name s6-bench --network s6-net --memory 1g --cpus 2 \
    -v "$ROOT:/work" -e STORE_LIMITS="$(limits tikv)" "$IMAGE" bench.Bench
}

start_ui() {
  podman rm -f s6-ui >/dev/null 2>&1 || true
  podman run -d --name s6-ui --network s6-net --memory 512m --cpus 1 \
    -p "$(service_port ui):8080" -v "$ROOT:/work:ro" "$IMAGE" bench.UiServer
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
