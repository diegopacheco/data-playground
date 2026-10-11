#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPTS="$ROOT/scripts"
RUN="$ROOT/.run"
LOGS="$RUN/logs"
cd "$ROOT"

mkdir -p "$RUN" "$LOGS"

KAFKA_CONTAINER=i7-kafka
TOPIC=i7-orders
GROUP=i7-paimon-pipeline
WAREHOUSE="$ROOT/warehouse"
SDK_JAVA="$HOME/.sdkman/candidates/java/25.0.4-amzn"
if [ -d "$SDK_JAVA" ]; then
  export JAVA_HOME="$SDK_JAVA"
  export PATH="$JAVA_HOME/bin:$PATH"
fi
JAVA_OPENS="--add-opens=java.base/java.lang=ALL-UNNAMED --add-opens=java.base/java.util=ALL-UNNAMED --add-opens=java.base/java.nio=ALL-UNNAMED --add-opens=java.base/sun.nio.ch=ALL-UNNAMED --add-opens=java.base/java.lang.reflect=ALL-UNNAMED --add-opens=java.base/java.io=ALL-UNNAMED --add-opens=java.base/java.net=ALL-UNNAMED --add-opens=java.base/java.time=ALL-UNNAMED --add-opens=java.base/java.math=ALL-UNNAMED --add-opens=java.base/java.util.concurrent=ALL-UNNAMED --add-opens=java.base/java.util.concurrent.atomic=ALL-UNNAMED --add-opens=java.base/jdk.internal.misc=ALL-UNNAMED --enable-native-access=ALL-UNNAMED"
CLASSPATH_APP="$ROOT/target/classes:$ROOT/target/lib/*"

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
    kafka) printf "kafka://localhost:%s\n" "$port" ;;
    *) printf "http://localhost:%s\n" "$port" ;;
  esac
}

jvm() {
  local main heap
  main="$1"
  heap="$2"
  shift 2
  exec java $JAVA_OPENS "-Xmx$heap" "-Dwarehouse=$WAREHOUSE" "-Dbootstrap=localhost:$(service_port kafka)" "-Dtopic=$TOPIC" "-Dport=$(service_port ui)" -cp "$CLASSPATH_APP" "com.github.diegopacheco.paimonflink.$main" "$@"
}

sql() {
  ( jvm SqlConsole 384m "$@" 2>>"$LOGS/sql.log" )
}

port_pid() {
  lsof -ti "tcp:$1" -sTCP:LISTEN 2>/dev/null | head -1 || true
}

port_up() {
  [ -n "$(port_pid "$1")" ]
}

pid_alive() {
  [ -f "$RUN/$1.pid" ] && kill -0 "$(cat "$RUN/$1.pid")" 2>/dev/null
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

kafka_cli() {
  local tool
  tool="$1"
  shift
  podman exec -i "$KAFKA_CONTAINER" "/opt/kafka/bin/$tool" --bootstrap-server localhost:29092 "$@"
}

wait_kafka_ready() {
  local tries
  tries="${1:-60}"
  while [ "$tries" -gt 0 ]; do
    if kafka_cli kafka-topics.sh --list >/dev/null 2>&1; then return 0; fi
    sleep 1
    tries=$((tries - 1))
  done
  return 1
}

topic_exists() {
  kafka_cli kafka-topics.sh --list 2>/dev/null | grep -qx "$TOPIC"
}

create_topic() {
  local tries
  tries=60
  while [ "$tries" -gt 0 ]; do
    if topic_exists; then return 0; fi
    kafka_cli kafka-topics.sh --create --if-not-exists --topic "$TOPIC" --partitions 1 --replication-factor 1 >/dev/null 2>&1 || true
    sleep 1
    tries=$((tries - 1))
  done
  fail "topic $TOPIC was not created"
}

delete_topic() {
  local tries
  tries=60
  kafka_cli kafka-consumer-groups.sh --delete --group "$GROUP" >/dev/null 2>&1 || true
  kafka_cli kafka-topics.sh --delete --if-exists --topic "$TOPIC" >/dev/null 2>&1 || true
  while [ "$tries" -gt 0 ]; do
    if ! topic_exists; then return 0; fi
    sleep 1
    tries=$((tries - 1))
  done
  fail "topic $TOPIC was not deleted"
}

produce() {
  tail -n +2 "$1" | sed '/^$/d' | kafka_cli kafka-console-producer.sh --topic "$TOPIC" >/dev/null || fail "producing $1 failed"
  log "produced $(tail -n +2 "$1" | sed '/^$/d' | wc -l | tr -d ' ') records from $(basename "$1") into $TOPIC"
}

start_bg() {
  local name
  name="$1"
  shift
  if pid_alive "$name"; then
    log "$name already running"
    return 0
  fi
  ( "$@" >"$LOGS/$name.log" 2>&1 ) &
  echo $! >"$RUN/$name.pid"
  log "$name started pid $!"
}

stop_bg() {
  local name pid port tries
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

start_pipeline() {
  start_bg pipeline jvm Pipeline 512m
}

build_app() {
  require mvn
  mvn -q -DskipTests package || fail "maven build failed"
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
