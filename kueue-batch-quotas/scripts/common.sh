#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPTS="$ROOT/scripts"
RUN="$ROOT/.run"
RESULTS="$RUN/results"
VENDOR="$RUN/vendor"
CLUSTER="kueue-batch-quotas"
CTX="kind-$CLUSTER"
KUEUE_VERSION="v0.20.5"
KUEUE_RELEASE="https://github.com/kubernetes-sigs/kueue/releases/download/$KUEUE_VERSION"
KUEUE_IMAGE="registry.k8s.io/kueue/kueue:$KUEUE_VERSION"
KUEUEVIZ_BACKEND_IMAGE="registry.k8s.io/kueue/kueueviz-backend:$KUEUE_VERSION"
KUEUEVIZ_FRONTEND_IMAGE="registry.k8s.io/kueue/kueueviz-frontend:$KUEUE_VERSION"
PY_IMAGE="localhost/$CLUSTER-python:v1"
JAVA_IMAGE="localhost/$CLUSTER-java:v1"
JAVA_HOME="$HOME/.sdkman/candidates/java/25.0.4-amzn"
PATH="$JAVA_HOME/bin:$PATH"
export KIND_EXPERIMENTAL_PROVIDER=podman JAVA_HOME PATH
cd "$ROOT"
mkdir -p "$RUN/logs" "$RESULTS" "$VENDOR"

SERVICES="$(grep '=' "$SCRIPTS/ports.env" || true)"

service_names() {
  printf "%s\n" "$SERVICES" | sed '/^$/d' | cut -d= -f1
}

service_port() {
  printf "%s\n" "$SERVICES" | awk -F= -v n="$1" '$1==n{print $2; exit}'
}

service_url() {
  case "$1" in
    kueueviz-backend) printf "ws://localhost:%s\n" "$(service_port "$1")" ;;
    *) printf "http://localhost:%s\n" "$(service_port "$1")" ;;
  esac
}

service_target() {
  case "$1" in
    kueueviz) printf "%s\n" "svc/kueue-kueueviz-frontend" ;;
    kueueviz-backend) printf "%s\n" "svc/kueue-kueueviz-backend" ;;
  esac
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

deployment_ready() {
  local ready
  ready="$(k -n kueue-system get deployment "$1" -o jsonpath='{.status.readyReplicas}' 2>/dev/null || true)"
  [ -n "$ready" ] && [ "$ready" -ge 1 ]
}

kueue_ready() {
  deployment_ready kueue-controller-manager
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

vendor_file() {
  local target
  target="$VENDOR/$KUEUE_VERSION-$1"
  if [ ! -s "$target" ]; then
    curl -fsSL -o "$target.tmp" "$KUEUE_RELEASE/$1" || fail "download $1 failed"
    mv "$target.tmp" "$target"
  fi
  printf "%s\n" "$target"
}

e2e_env() {
  KUBE_CONTEXT="$CTX" PY_IMAGE="$PY_IMAGE" JAVA_IMAGE="$JAVA_IMAGE" RESULTS_DIR="$RESULTS" REPORT_DIR="$RUN" "$@"
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
