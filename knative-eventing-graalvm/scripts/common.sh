#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPTS="$ROOT/scripts"
RUN="$ROOT/.run"
CLUSTER="knative-eventing-graalvm"
CTX="kind-$CLUSTER"
KNATIVE="knative-v1.24.0"
SERVING_URL="https://github.com/knative/serving/releases/download/$KNATIVE"
KOURIER_URL="https://github.com/knative-extensions/net-kourier/releases/download/$KNATIVE"
EVENTING_URL="https://github.com/knative/eventing/releases/download/$KNATIVE"
KAFKA_EVENTING_URL="https://github.com/knative-extensions/eventing-kafka-broker/releases/download/$KNATIVE"
KAFKA_IMAGE="docker.io/apache/kafka:4.4.0"
IMAGE_PREFIX="kind.local/$CLUSTER"
VARIANTS="native jvm jvm-aot python"
JAVA_HOME="$HOME/.sdkman/candidates/java/25.0.4-amzn"
PATH="$JAVA_HOME/bin:$PATH"
export KIND_EXPERIMENTAL_PROVIDER=podman JAVA_HOME PATH
cd "$ROOT"
mkdir -p "$RUN/logs"

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

service_target() {
  case "$1" in
    lab) printf "%s\n" "svc/lab 8080" ;;
  esac
}

image_for() {
  printf "%s-%s:v1\n" "$IMAGE_PREFIX" "$1"
}

forward_pid() {
  local f
  f="$RUN/$1.pid"
  [ -f "$f" ] && kill -0 "$(cat "$f")" 2>/dev/null && cat "$f" || true
}

k() {
  kubectl --context "$CTX" "$@"
}

cluster_exists() {
  local clusters
  clusters="$(kind get clusters 2>/dev/null || true)"
  printf "%s\n" "$clusters" | grep -x "$CLUSTER" >/dev/null
}

deployments_ready() {
  local rows
  rows="$(k get deployments -n "$1" --no-headers -o custom-columns=R:.status.readyReplicas,D:.spec.replicas 2>/dev/null)" || return 1
  [ -n "$rows" ] || return 1
  printf "%s\n" "$rows" | awk '{r=($1=="<none>")?0:$1} r!=$2{bad=1} END{exit bad}'
}

wait_deployments() {
  local i
  for i in 1 2 3 4 5; do
    if wait_until 60 deployments_ready "$1"; then return 0; fi
    log "still waiting for deployments in $1 ($i/5)"
  done
  return 1
}

kafka_ready() {
  [ "$(k get statefulset kafka -o jsonpath='{.status.readyReplicas}' 2>/dev/null)" = "1" ]
}

condition_ready() {
  [ "$(k get "$1" "$2" -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}' 2>/dev/null)" = "True" ]
}

port_pid() {
  lsof -ti "tcp:$1" -sTCP:LISTEN 2>/dev/null | head -1 || true
}

port_up() {
  [ -n "$(port_pid "$1")" ]
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

wait_long() {
  wait_until 60 "$@" || wait_until 60 "$@" || wait_until 60 "$@"
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

load_image() {
  local tar
  tar="$RUN/$(printf "%s" "$1" | tr '/:' '__').tar"
  podman save -o "$tar" "$1" || fail "podman save $1 failed"
  kind load image-archive "$tar" --name "$CLUSTER" || fail "kind load $1 failed"
  rm -f "$tar"
}

e2e_env() {
  KUBE_CONTEXT="$CTX" LAB_URL="$(service_url lab)" IMAGE_PREFIX="$IMAGE_PREFIX" RESULTS_DIR="$RUN" "$@"
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
