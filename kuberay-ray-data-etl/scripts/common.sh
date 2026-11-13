#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPTS="$ROOT/scripts"
RUN="$ROOT/.run"
CLUSTER="kuberay-ray-data-etl"
CTX="kind-$CLUSTER"
KUBERAY_VERSION="1.7.2"
KUBERAY_REPO="https://ray-project.github.io/kuberay-helm/"
OPERATOR_IMAGE="quay.io/kuberay/operator:v$KUBERAY_VERSION"
RAY_IMAGE="docker.io/rayproject/ray:2.60.0-py314"
MINIO_IMAGE="docker.io/pgsty/minio:RELEASE.2026-08-04T00-00-00Z"
JRE_IMAGE="docker.io/library/eclipse-temurin:25.0.4.1_1-jre-noble"
ETL_IMAGE="localhost/$CLUSTER-etl:v1"
PRODUCER_IMAGE="localhost/$CLUSTER-producer:v1"
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
    ray-dashboard) printf "%s\n" "svc/etl-head-svc 8265" ;;
    minio-api) printf "%s\n" "svc/minio 9000" ;;
    minio-console) printf "%s\n" "svc/minio 9001" ;;
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
  local ready
  ready="$(k -n "$1" get deploy "$2" -o jsonpath='{.status.readyReplicas}' 2>/dev/null || true)"
  [ -n "$ready" ] && [ "$ready" -ge 1 ]
}

ray_cluster_state() {
  k get raycluster etl -o jsonpath='{.status.state}' 2>/dev/null || true
}

ray_cluster_ready() {
  [ "$(ray_cluster_state)" = "ready" ]
}

ray_job_status() {
  k get rayjob etl-driver -o jsonpath='{.status.jobDeploymentStatus}/{.status.jobStatus}' 2>/dev/null || true
}

ray_job_running() {
  [ "$(ray_job_status)" = "Running/RUNNING" ]
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
