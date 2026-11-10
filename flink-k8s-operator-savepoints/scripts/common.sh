#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPTS="$ROOT/scripts"
RUN="$ROOT/.run"
CLUSTER="flink-k8s-operator-savepoints"
CTX="kind-$CLUSTER"
FLINK_IMAGE="docker.io/library/flink:2.3.0-scala_2.12-java21"
JAVA_IMAGE="localhost/$CLUSTER-java:v1"
PY_IMAGE="localhost/$CLUSTER-python:v1"
OPERATOR_VERSION="1.16.1"
OPERATOR_IMAGE="ghcr.io/apache/flink-kubernetes-operator:$OPERATOR_VERSION"
OPERATOR_CHART="https://archive.apache.org/dist/flink/flink-kubernetes-operator-$OPERATOR_VERSION/flink-kubernetes-operator-$OPERATOR_VERSION-helm.tgz"
CERT_MANAGER_VERSION="v1.21.3"
CERT_MANAGER_MANIFEST="https://github.com/cert-manager/cert-manager/releases/download/$CERT_MANAGER_VERSION/cert-manager.yaml"
CERT_MANAGER_IMAGES="quay.io/jetstack/cert-manager-controller:$CERT_MANAGER_VERSION quay.io/jetstack/cert-manager-webhook:$CERT_MANAGER_VERSION quay.io/jetstack/cert-manager-cainjector:$CERT_MANAGER_VERSION"
JOBS="clicks-java clicks-python"
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
    java-ui) printf "%s\n" "svc/clicks-java-rest 8081" ;;
    python-ui) printf "%s\n" "svc/clicks-python-rest 8081" ;;
  esac
}

k() {
  kubectl --context "$CTX" "$@"
}

cluster_exists() {
  local clusters
  clusters="$(kind get clusters 2>/dev/null || true)"
  printf "%s\n" "$clusters" | grep -x "$CLUSTER" >/dev/null
}

deploy_ready() {
  [ "$(k -n "$1" get deploy "$2" -o jsonpath='{.status.readyReplicas}' 2>/dev/null)" = "1" ]
}

job_state() {
  k get flinkdeployment "$1" -o jsonpath='{.status.jobStatus.state}' 2>/dev/null || true
}

job_running() {
  [ "$(job_state "$1")" = "RUNNING" ]
}

pidfile_pid() {
  local f
  f="$RUN/$1.pid"
  [ -f "$f" ] && kill -0 "$(cat "$f")" 2>/dev/null && cat "$f" || true
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
  local rounds
  rounds="$1"
  shift
  while [ "$rounds" -gt 0 ]; do
    if wait_until 60 "$@"; then return 0; fi
    rounds=$((rounds - 1))
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

load_image() {
  local tar
  tar="$RUN/$(printf "%s" "$1" | tr '/:' '__').tar"
  podman save -o "$tar" "$1" || fail "podman save $1 failed"
  kind load image-archive "$tar" --name "$CLUSTER" || fail "kind load $1 failed"
  rm -f "$tar"
}

open_url() {
  if command -v open >/dev/null 2>&1; then open "$1"; else xdg-open "$1"; fi
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
