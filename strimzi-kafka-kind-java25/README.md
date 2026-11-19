<p align="center"><img src="https://github.com/strimzi.png" alt="Strimzi" width="120"></p>

# strimzi-kafka-kind-java25

Apache Kafka 4.3.2 run by the Strimzi 1.3.1 operator on a local kind cluster, in KRaft mode with two `KafkaNodePool`s (3 controllers, 3 brokers). The topic and the users exist only as Kubernetes YAML (`KafkaTopic`, `KafkaUser` with SCRAM-SHA-512 and ACLs). A Java 25 Spring Boot 4.1 producer sends orders, one virtual thread per send, and a Python 3.15 consumer counts them. Both run as pods and log in with their own Strimzi-generated credentials.

Two end-to-end tests prove the operational claims:

* A rolling restart of every broker while the producer keeps sending loses nothing: produced == acked == distinct keys consumed.
* Scaling the broker pool from 3 to 4 and running a `KafkaRebalance` (Cruise Control, `add-brokers`) moves partition replicas and leaders onto the new broker, then `remove-brokers` drains it so the pool can go back to 3.

## How it Works

1. `scripts/setup.sh` creates the kind cluster (1 control plane, 2 workers), installs the Strimzi 1.3.1 cluster operator into namespace `kafka` and applies `k8s/kafka.yaml`: the `Kafka` resource `orders-cluster`, node pool `controllers` (3, KRaft) and node pool `brokers` (3), a SCRAM-SHA-512 listener on 9092, simple authorization, the entity operator and Cruise Control.
2. It applies `k8s/topics.yaml` (topic `orders`, 12 partitions, RF 3, `min.insync.replicas=2`) and `k8s/users.yaml` (users `order-producer`, `order-consumer`, `cluster-inspector`). The user operator creates the SCRAM users, ACLs and one Secret per user.
3. It builds the producer jar with Maven on JDK 25, builds both images with podman and loads them into kind.
4. `scripts/start-all.sh` deploys `k8s/apps.yaml` and port-forwards the producer to `localhost:27510`.
5. The producer reads `sasl.jaas.config` from the `order-producer` Secret; the consumer reads `password` from the `order-consumer` Secret.
6. `POST /runs/{runId}?rate=N` starts a run: a virtual thread paces N orders per second and hands each send to its own virtual thread that blocks on the broker ack. `DELETE /runs/{runId}` stops the run and returns only after every in-flight send finished.
7. The consumer commits after each poll (at-least-once) and logs `{"run", "received", "distinct"}` per run once a second.
8. The e2e tests drive the producer over HTTP and the cluster with `kubectl`, then compare the producer's acked count with the consumer's distinct key count.

## Architecture

![Architecture](architecture.svg)

## Features

* KRaft with node pools: controllers and brokers are separate pools, so brokers scale and roll without touching the quorum.
* Topic and users as YAML only: `auto.create.topics.enable=false`, and the apps have no admin rights, so the YAML is the single source of truth.
* SCRAM-SHA-512 per app with least-privilege ACLs: the producer can only write `orders`, the consumer can only read `orders` with group `order-counter`, the inspector can only describe.
* Credentials from Strimzi Secrets: no password is written anywhere in the repo.
* No-loss producer: `acks=all`, idempotence on, long delivery timeout, so a broker restart becomes a retry instead of a lost order.
* Virtual threads: one cheap thread per in-flight send, blocking code with no callback plumbing.
* Rolling restart by annotation: `strimzi.io/manual-rolling-update=true` on the `orders-cluster-brokers` StrimziPodSet; Strimzi restarts one broker at a time and waits for partitions to be back in sync.
* Partition reassignment with Cruise Control: `KafkaRebalance` in `add-brokers` and `remove-brokers` mode with auto-approval.
* Loss check by distinct keys: every key is `runId-seq`, so redelivered messages after a group rebalance never hide a missing one.

## Stack

* Strimzi 1.3.1: Kubernetes operator for Kafka, only `v1` CRDs.
* Apache Kafka 4.3.2 (Strimzi image), KRaft, metadata version `4.3-IV0`.
* Cruise Control (bundled with Strimzi 1.3.1): computes and executes partition moves.
* Java 25 (Temurin 25.0.5 JRE in the image, JDK 25.0.4 to build): producer runtime.
* Spring Boot 4.1.2 with Spring Kafka 4.1.2 and kafka-clients 4.2.2 (managed by Boot): HTTP API and Kafka template.
* Python 3.15.2 (`python:3.15.2-slim`) with uv 0.10.4: consumer runtime.
* kafka-python 3.0.13: pure Python client, works on 3.15 (confluent-kafka 2.16.1 ships no cp315 wheels).
* pytest 9.2.0 and ty 0.0.99: tests and type checks for the consumer and the e2e harness.
* kind 0.31 on podman: local Kubernetes 1.35.

## Contracts

Producer API, port-forwarded to `http://localhost:27510`:

| Method | Path | What it does |
|---|---|---|
| `GET` | `/runs` | All runs with their counters |
| `POST` | `/runs/{runId}?rate=200` | Starts sending `rate` orders per second. `201`, or `409` if the run id was used, `400` for a bad id or rate |
| `GET` | `/runs/{runId}` | Current counters |
| `DELETE` | `/runs/{runId}` | Stops the run, waits for all in-flight sends, returns the final counters |

```json
{"runId":"roll-1","ratePerSecond":200,"sent":38476,"acked":38476,"failed":0,"running":false,"lastError":""}
```

Kafka record on topic `orders`, key `runId-seq`:

```json
{"runId":"roll-1","seq":3,"sku":"sku-3","qty":4,"priceCents":211}
```

Consumer log line, one per changed run per second:

```json
{"run": "roll-1", "received": 38476, "distinct": 38476}
```

## Design decisions

* Separate controller and broker pools. The rolling restart and the scale out touch only brokers, the KRaft quorum stays stable.
* Persistent volumes (kind `standard` local-path) for brokers. With ephemeral storage every restarted broker would come back empty and copy all its data again.
* Distinct keys, not raw counts. A consumer group rebalance during a roll can redeliver messages that were processed but not committed; counting distinct keys proves no loss, and `received - distinct` shows the duplicates.
* The producer counts `acked` only after the broker confirmed the write with `acks=all`, so the number compared against the consumer is what Kafka promised to keep.
* The e2e harness reads partition layout with `kafka-topics.sh --describe` inside a broker pod, using the `cluster-inspector` user. Its SCRAM config is piped in on stdin and deleted after use, so no password is passed as a command line argument.
* The reassignment test cleans up after itself: `remove-brokers` drains the new broker, then the pool goes back to 3, so `test-all.sh` can run again.
* Cruise Control metric windows are shortened (60 s sampling, 60 s windows, 2 windows) so a proposal is ready within a few minutes of a fresh cluster.
* The reassignment test waits for Cruise Control to restart after the scale up before it creates the `KafkaRebalance`, because Cruise Control only reads broker capacities at start.

## Results

Measured with `./scripts/test-all.sh` on kind (podman, 1 control plane, 2 workers) on an arm64 laptop. The two e2e tests took 594 s together.

### Rolling restart of all 3 brokers while producing

| Metric | Value |
|---|---|
| Producer rate | 200 orders/s |
| Time for Strimzi to roll all 3 brokers, one at a time | 172 s |
| Orders produced | 38476 |
| Orders acked by Kafka (`acks=all`) | 38476 |
| Failed sends | 0 |
| Records consumed | 38476 |
| Distinct keys consumed | 38476 |
| Duplicates | 0 |
| Consumer caught up after the producer stopped | 2 s |

Produced == acked == distinct consumed: no order was lost while every broker was restarted.

### Partition reassignment with Cruise Control

| Step | Time |
|---|---|
| Scale `brokers` pool 3 to 4 (new broker id 6 Ready) | 23 s |
| Cruise Control restarted with the capacity of broker 6 | 25 s |
| `KafkaRebalance` add-brokers [6], proposal plus execution | 222 s |
| `KafkaRebalance` remove-brokers [6], drain | 121 s |
| Scale `brokers` pool 4 to 3 | 2 s |

The add-brokers proposal moved 104 replicas (59 MB, all topics including `__consumer_offsets`) and 0 explicit leader moves.

Topic `orders` before (brokers 0, 1, 2):

```
p0   leader=0 replicas=0,1,2      p6   leader=2 replicas=2,1,0
p1   leader=1 replicas=1,2,0      p7   leader=1 replicas=1,0,2
p2   leader=2 replicas=2,0,1      p8   leader=0 replicas=0,2,1
p3   leader=1 replicas=1,2,0      p9   leader=0 replicas=0,1,2
p4   leader=2 replicas=2,0,1      p10  leader=1 replicas=1,2,0
p5   leader=0 replicas=0,1,2      p11  leader=2 replicas=2,0,1
replicas per broker {0: 12, 1: 12, 2: 12}   leaders per broker {0: 4, 1: 4, 2: 4}
```

Topic `orders` after add-brokers [6]:

```
p0   leader=0 replicas=0,6,2      p6   leader=2 replicas=2,1,6
p1   leader=1 replicas=1,6,0      p7   leader=1 replicas=1,0,6
p2   leader=2 replicas=2,6,1      p8   leader=6 replicas=6,2,1
p3   leader=1 replicas=1,6,0      p9   leader=6 replicas=6,1,2
p4   leader=2 replicas=2,0,6      p10  leader=6 replicas=6,2,0
p5   leader=0 replicas=0,1,6      p11  leader=2 replicas=2,0,6
replicas per broker {0: 8, 1: 8, 2: 8, 6: 12}   leaders per broker {0: 2, 1: 3, 2: 4, 6: 3}
```

Broker 6 went from 0 to 12 replicas and 3 leaders of `orders`, every partition kept 3 in-sync replicas. After remove-brokers it held 0 again and the pool went back to brokers 0, 1, 2.

### Things learned on the way

* `strimzi.io/manual-rolling-update=true` has no effect on a `KafkaNodePool`. Strimzi only acts on it when it is on the `StrimziPodSet` (`orders-cluster-brokers`) or on a single pod, and picks it up on the next reconciliation.
* Right after a scale up, Strimzi restarts Cruise Control so it learns the capacity of the new broker. A `KafkaRebalance` sent before that restart fails with a `NullPointerException` on `BrokerCapacityInfo`, so the test waits for a Cruise Control pod newer than the new broker pod.
* Cruise Control refuses a `metric.sampling.interval.ms` below its 55 s metadata refresh timeout, so 60 s is the shortest working value.

## How to run

Requirements: podman, kind, kubectl, Maven, JDK 25, uv, curl, lsof.

```bash
./scripts/setup.sh
./scripts/start-all.sh
./scripts/test-all.sh
./scripts/stop-all.sh
./scripts/teardown.sh
```

`test-all.sh` runs:

* `mvn test` for the producer: unique keys per run and across runs, the order JSON, `stop` waiting for in-flight sends, failures never counted as acked, rate pacing, run id and rate validation.
* `pytest` and `ty check` for the consumer: redelivered keys do not inflate the distinct count, runs are counted apart, payloads without a run id are not counted, credentials come from env.
* `pytest` and `ty check` for the e2e harness parser of `kafka-topics.sh --describe`.
* `e2e/tests/cluster/test_a_rolling_restart.py` and `e2e/tests/cluster/test_b_partition_reassignment.py` against the running cluster.

Start a run by hand:

```bash
curl -X POST "http://localhost:27510/runs/manual-1?rate=100"
curl "http://localhost:27510/runs/manual-1"
curl -X DELETE "http://localhost:27510/runs/manual-1"
kubectl --context kind-strimzi-kafka-kind-java25 -n kafka logs deploy/order-consumer --tail=5
```

## Scripts

All scripts live in `scripts/` and run from any directory of the repository.

| Script | What it does |
|---|---|
| `./scripts/setup.sh` | Creates the kind cluster, installs Strimzi, creates Kafka, the topic and the users, builds and loads both images |
| `./scripts/start-all.sh` | Deploys the producer and the consumer, port-forwards the producer and prints its full link |
| `./scripts/status.sh` | Shows the cluster, Kafka readiness, broker ids, both apps and every port as UP or DOWN |
| `./scripts/test-all.sh` | Runs the unit tests, type checks and the end-to-end tests on the cluster |
| `./scripts/stop-all.sh` | Stops the port-forward and deletes the producer and the consumer, Kafka keeps running |
| `./scripts/teardown.sh` | Stops everything, deletes the kind cluster and the local images |

Ports are declared in `scripts/ports.env`: `producer=27510` (`http://localhost:27510/runs`).

```bash
./scripts/setup.sh
./scripts/start-all.sh
./scripts/status.sh
./scripts/stop-all.sh
./scripts/teardown.sh
```
