#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

patch_config() {
  k patch configmap "$1" -n knative-serving --type merge -p "$2" >/dev/null || fail "patch $1 failed"
}

for tool in podman kind kubectl uv mvn lsof; do require "$tool"; done
[ -x "$JAVA_HOME/bin/java" ] || fail "Java 25 not found at $JAVA_HOME"

if cluster_exists; then
  log "kind cluster $CLUSTER already exists"
else
  kind create cluster --config "$ROOT/k8s/kind.yaml" || fail "kind create cluster failed"
fi

log "syncing python projects"
for project in python-service lab e2e; do
  (cd "$ROOT/$project" && uv sync --python 3.15 --quiet) || fail "uv sync $project failed"
done

log "building the GraalVM native image, the JVM image and the JVM image with a JDK 25 AOT cache"
for variant in native jvm jvm-aot; do
  podman build --target "$variant" -t "$(image_for "$variant")" -f "$ROOT/java-service/Containerfile" "$ROOT/java-service" || fail "$variant image build failed"
done
podman build -t "$(image_for python)" -f "$ROOT/python-service/Containerfile" "$ROOT/python-service" || fail "python image build failed"
podman build -t "$(image_for lab)" -f "$ROOT/lab/Containerfile" "$ROOT/lab" || fail "lab image build failed"
podman image exists "$KAFKA_IMAGE" || podman pull "$KAFKA_IMAGE" || fail "pull $KAFKA_IMAGE failed"

for image in "$KAFKA_IMAGE" $(for v in $VARIANTS lab; do image_for "$v"; done); do
  log "loading $image into kind"
  load_image "$image"
done

log "installing Knative Serving $KNATIVE with Kourier"
k apply -f "$SERVING_URL/serving-crds.yaml" >/dev/null || fail "serving crds failed"
k apply -f "$SERVING_URL/serving-core.yaml" >/dev/null || fail "serving core failed"
k apply -f "$KOURIER_URL/kourier.yaml" >/dev/null || fail "kourier failed"
wait_deployments knative-serving || fail "knative-serving not ready"
wait_deployments kourier-system || fail "kourier not ready"
patch_config config-network '{"data":{"ingress-class":"kourier.ingress.networking.knative.dev"}}'
patch_config config-deployment '{"data":{"registries-skipping-tag-resolving":"kind.local,ko.local,dev.local,localhost"}}'
patch_config config-autoscaler '{"data":{"scale-to-zero-grace-period":"10s","stable-window":"6s"}}'

log "installing Knative Eventing $KNATIVE with the Kafka source"
k apply -f "$EVENTING_URL/eventing-crds.yaml" >/dev/null || fail "eventing crds failed"
k apply -f "$EVENTING_URL/eventing-core.yaml" >/dev/null || fail "eventing core failed"
wait_deployments knative-eventing || fail "knative-eventing not ready"
k apply -f "$KAFKA_EVENTING_URL/eventing-kafka-controller.yaml" >/dev/null || fail "kafka controller failed"
k apply -f "$KAFKA_EVENTING_URL/eventing-kafka-source.yaml" >/dev/null || fail "kafka source failed"
wait_deployments knative-eventing || fail "knative-eventing kafka components not ready"
log "setup done"
