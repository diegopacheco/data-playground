<p align="center"><img src="https://raw.githubusercontent.com/knative/docs/main/docs/images/logo/rgb/knative-logo-rgb.png" alt="Knative" width="260"></p>

# knative-eventing-graalvm

Knative Serving and Knative Eventing 1.24.0 (Kourier as the networking layer) on a local kind cluster with a single-broker Apache Kafka 4.4.0. Four KafkaSources (eventing-kafka-broker 1.24.0) deliver CloudEvents from four Kafka topics to four Knative Services that run the same small order transform and scale to zero: a Java 25 Spring Boot 4.1 app compiled to a GraalVM native image, the same app on the JVM, the same app on the JVM with a JDK 25 AOT cache, and a Python 3.15 Granian ASGI app. The end-to-end tests prove that every event on a topic is handled exactly once and that every service goes to zero and comes back on the next event. A benchmark measures the cold start (event produced to event handled, split into scale-up, app start and first request), the warm latency, the image size and the memory of each variant.

## How it Works

1. `scripts/setup.sh` creates the kind cluster, builds the five images (three targets of `java-service/Containerfile`, the Python service, the lab), loads them and `apache/kafka:4.4.0` into kind, installs Knative Serving + Kourier, patches `config-network`, `config-deployment` and `config-autoscaler`, then installs Knative Eventing and the Kafka source.
2. `scripts/start-all.sh` starts Kafka (StatefulSet + PVC), creates the topics `orders-native`, `orders-jvm`, `orders-jvm-aot`, `orders-python`, starts the `lab` Deployment, applies the four Knative Services and the four KafkaSources and port-forwards the lab to `localhost:27630`.
3. The host (tests or benchmark) calls `POST /produce` on the lab. The lab stamps `producedAtMs` right before each Kafka send and writes the record with CloudEvent binary headers (`ce_id`, `ce_type`, `content-type: application/json`).
4. The `kafka-source-dispatcher` reads the topic, turns each record into a CloudEvent and POSTs it to `orders-<variant>.default.svc.cluster.local` through `kourier-internal`. At zero pods the activator holds the request and the autoscaler starts a pod.
5. The service parses the order, computes `totalCents = quantity * unitPriceCents` and upper-cases the SKU, then POSTs a record to the lab with its pod name, process start time (`/proc/self/stat` + `/proc/uptime`), ready time (Spring `ApplicationReadyEvent` or ASGI lifespan startup), handled time, RSS and cgroup memory. It answers 200 only after the lab accepted the record, so a failed report is retried by the source.
6. Every service has `min-scale 0`, `max-scale 1`, a 6 s window and `scale-to-zero-pod-retention-period 0s`, with a 10 s cluster-wide grace period, so an idle service is at zero about 20 to 40 s after its last event.
7. All timestamps come from pods on the same kind node, so they share one kernel clock and the host clock never enters a latency number.

## Architecture

![Architecture](architecture.svg)

## Features

* Same transform, four runtimes: one Spring Boot code base builds three images, the Python app implements the same contract, so differences come from the runtime only.
* Exactly-once proof: the tests compare the produced ids with the handled ids per variant, fail on any missing id or duplicate, and check the computed total and SKU for every event.
* Real cold starts only: a measurement is rejected unless `producedAt <= processStart <= ready <= handled`, which proves a fresh process started after the event.
* Cold start breakdown: scale-up (Knative + Kubernetes + container runtime), app start (inside the process) and first request (readiness to handled), so it is clear where the time goes.
* In-cluster clock: the lab stamps produce time and the services stamp process start, ready and handled time, all on the same node clock.
* One topic and one KafkaSource per variant: a cold start of one variant never wakes another one.

## Stack

* Kubernetes v1.35.0 (`kindest/node`, kind v0.31 on podman), one node.
* Knative Serving 1.24.0 + net-kourier 1.24.0: request driven scale to zero, Kourier is the lightest ingress.
* Knative Eventing 1.24.0 + eventing-kafka-broker 1.24.0 (`eventing-kafka-controller.yaml` + `eventing-kafka-source.yaml`): the KafkaSource.
* Apache Kafka 4.4.0 (`docker.io/apache/kafka:4.4.0`, KRaft combined broker + controller, no operator), same as the sibling POCs.
* Java 25, Spring Boot 4.1.2 (`spring-boot-starter-webmvc`, Tomcat, virtual threads), Jackson 3, `java.net.http` for the lab call, no other libraries.
* GraalVM CE for JDK 25 (`ghcr.io/graalvm/native-image-community:25i4-25.0.4.1.1-ol10-20260922`, linux arm64) with the Spring Boot `native` profile and native-maven-plugin, runtime `debian:trixie-20261104-slim`.
* JVM runtime `eclipse-temurin:25.0.5_8-jre`, Maven build in `maven:3.9.16-eclipse-temurin-25`.
* Python 3.15.2 (`python:3.15.2-slim`), uv 0.13.7, Granian 2.8.7 (ASGI, has `cp315` aarch64 wheels), standard library only in the handler.
* Lab: Python 3.15 + Granian + kafka-python 3.0.13 (pure Python, no 3.15 wheel needed).
* pytest 9.2.0, ty 0.0.99, JUnit (from Spring Boot test starter).

## Contracts and design decisions

Kafka record (topic `orders-<variant>`, key = id, headers `ce_specversion=1.0`, `ce_id`, `ce_source=/lab`, `ce_type=orders.created`, `content-type=application/json`):

```json
{"id": "uuid", "sku": " sku-3 ", "quantity": 4, "unitPriceCents": 103}
```

Service response and record sent to the lab `POST /records` (lab answers 204):

```json
{"variant": "native", "id": "uuid", "sku": "SKU-3", "totalCents": 412, "pod": "orders-native-00001-deployment-...",
 "startedAtMs": 0, "readyAtMs": 0, "handledAtMs": 0, "rssKb": 0, "cgroupBytes": 0}
```

Lab API: `POST /produce {"variant", "events": [...]}` returns `{"producedAtMs": [...]}`, `GET /records?variant=x` returns every record (duplicates kept) joined with `producedAtMs`, `DELETE /records?variant=x`, `GET /health`.

* Three JVM images from one Containerfile (`--target native|jvm|jvm-aot`): the code is identical, only the build differs.
* `jvm` and `jvm-aot` both run the extracted jar (`-Djarmode=tools extract`) with `-XX:+UseSerialGC -XX:MaxRAMPercentage=75`. `jvm-aot` adds a training run at image build (`-XX:AOTCacheOutput`, `-Dspring.context.exit=onRefresh`) and starts with `-XX:AOTMode=on -XX:AOTCache=...`, so the JVM refuses to start if the cache cannot be used instead of silently falling back. The GC is pinned because the training run and the 1 CPU pod would otherwise pick different GCs.
* `registries-skipping-tag-resolving` must contain the image registry. A `localhost/...` image is parsed by Knative as `index.docker.io/localhost/...` and fails digest resolution with 401, so the images are named `kind.local/knative-eventing-graalvm-*:v1`.
* Knative config maps are changed with `kubectl patch --type merge`. A full `kubectl apply` drops keys such as `queue-sidecar-image` and the Knative webhook rejects it.
* Every service gets the same resources: request 100m CPU / 128Mi, limit 1 CPU / 512Mi.
* The KafkaSource uses `initialOffset: earliest` so events produced while the consumer group is joining are not skipped, and 5 exponential retries.

## Java 25 and Python 3.15

Everything runs on Java 25 and Python 3.15, nothing is downgraded. The native image builder is GraalVM CE 25.0.4.1.1 (JDK 25), the JVM images use Temurin 25.0.5, unit tests run with Corretto 25.0.4. Granian 2.8.7 publishes `cp315` manylinux aarch64 wheels, so the Python image needs no compiler.

## How to run

```bash
./scripts/setup.sh
./scripts/start-all.sh
./scripts/test-all.sh
./scripts/bench.sh 7
./scripts/stop-all.sh
./scripts/teardown.sh
```

Unit tests alone: `cd java-service && mvn test`, `cd python-service && uv run pytest && uv run ty check`, `cd lab && uv run pytest && uv run ty check`.

## Results

Measured on a MacBook (Apple silicon) with a podman machine of 12 CPUs / 48 GB, one kind node shared with other clusters, `./scripts/bench.sh 7`: 7 rounds, every round waits until all four services have zero pods, then sends one event per variant (cold start) followed by 10 sequential warm events. 7 cold starts and 70 warm events per variant. Memory is read inside the user container after the warm events.

| Variant | Image MB | Cold total median / p95 ms | Scale-up median / p95 ms | App start median / p95 ms | First request median / p95 ms | Warm median / p95 ms | RSS MB | cgroup MB |
|---|---|---|---|---|---|---|---|---|
| native (GraalVM) | 172.9 | 1065 / 1236 | 417 / 439 | 67 / 69 | 574 / 769 | 160 / 193 | 70.5 | 20.7 |
| jvm | 409.9 | 2475 / 2691 | 413 / 561 | 1885 / 2135 | 125 / 190 | 160 / 192 | 190.8 | 169.2 |
| jvm-aot (JDK 25 AOT cache) | 465.9 | 1650 / 1836 | 422 / 613 | 1025 / 1113 | 180 / 184 | 158 / 193 | 191.6 | 163.8 |
| python (Granian) | 173.0 | 1133 / 1488 | 641 / 808 | 270 / 300 | 216 / 554 | 158 / 188 | 44.1 | 61.3 |

Raw cold totals (ms): native 665, 1226, 987, 1065, 577, 1128, 1236; jvm 2454, 2475, 2570, 2359, 2384, 2691, 2589; jvm-aot 1836, 1585, 1650, 1726, 1793, 1621, 1616; python 1133, 1462, 951, 1122, 1182, 1488, 1025.

* Column meaning: cold total = handled - produced; scale-up = process start - produced (dispatcher, activator, autoscaler, pod creation, container start); app start = ready - process start; first request = handled - ready.
* The native image starts Spring Boot in 67 ms against 1885 ms on the plain JVM (28x), and the JDK 25 AOT cache cuts the JVM start by 46% (1025 ms). End to end, native is 2.3x faster than the JVM and 1.5x faster than JVM + AOT cache.
* Once the app starts fast, Knative is the floor. Native spends ~0.4 s in scale-up and 0.1 to 0.8 s between "ready" and "handled" (queue-proxy readiness, endpoint update, activator forwarding). The JVM variants hide that step behind their own start, so their first request part is short. Python and native end up within 70 ms of each other at the median.
* Warm latency is the same (~160 ms) for every variant, so it does not come from the services. A direct HTTP POST from the lab pod to `orders-native` through `kourier-internal` takes 5 to 6 ms, and a Kafka produce with ack takes ~1.3 ms. The other ~150 ms is spent inside the `kafka-source-dispatcher` between the record landing in Kafka and the HTTP call. Switching to `delivery.order: unordered` and setting `fetch.max.wait.ms=10` did not change it (both changes were reverted). The root cause was not found in this POC.
* Memory: native RSS is 70 MB, against 191 MB for both JVM variants and 44 MB for Python. The cgroup number (`memory.current`) is lower than RSS for native because the 70 MB binary is file-backed page cache. That cache is charged to whichever cgroup read it first, and a previous pod read it.
* Image size: the native binary is 70 MB on a 103 MB Debian slim base. The JVM images carry a 370 MB JRE, and the AOT cache adds 56 MB.
* Build cost: `native-image` itself took 51 s with a peak RSS of 3.7 GiB in the builder stage (12 CPUs), on top of the Maven AOT processing. The JVM images only need `mvn package` and, for `jvm-aot`, a training run of about one second.

## Scripts

All scripts live in `scripts/` and run from any directory of the repository. The only host port is in `scripts/ports.env` (`lab=27630`).

| Script | What it does |
|---|---|
| `./scripts/setup.sh` | Creates the kind cluster, builds and loads the five images, installs Knative Serving + Kourier, Knative Eventing and the Kafka source |
| `./scripts/start-all.sh` | Starts Kafka, creates the topics, starts the lab, applies the Knative Services and KafkaSources, port-forwards the lab and prints its URL |
| `./scripts/status.sh` | Shows the cluster, the Knative components, Kafka, each service and source as READY or ABSENT with its pod count, and the port as UP or DOWN |
| `./scripts/test-all.sh` | Runs the Java, Python service and lab unit tests, ty on every Python project, then the end-to-end tests on kind |
| `./scripts/bench.sh [rounds]` | Runs the cold start benchmark (default 5 rounds), prints the table and writes `.run/bench.json` |
| `./scripts/stop-all.sh` | Stops the port-forward and deletes the sources, services, lab and Kafka (the Kafka PVC is kept) |
| `./scripts/teardown.sh` | Runs stop-all, deletes the kind cluster and removes the local images |
