import base64
from typing import Any

from harness.kube import apply, get_json, has_condition, kubectl, pod_ready
from harness.topology import Partition, parse_describe

CLUSTER = "orders-cluster"
BROKER_POOL = "brokers"
BROKER_PODSET = f"{CLUSTER}-{BROKER_POOL}"
INSPECTOR = "cluster-inspector"


def broker_pods() -> list[dict[str, Any]]:
    selector = f"strimzi.io/cluster={CLUSTER},strimzi.io/pool-name={BROKER_POOL}"
    return get_json("pods", "-l", selector)["items"]


def broker_pod_uids() -> dict[str, str]:
    return {p["metadata"]["name"]: p["metadata"]["uid"] for p in broker_pods()}


def ready_broker_count() -> int:
    return sum(1 for p in broker_pods() if pod_ready(p))


def broker_pool() -> dict[str, Any]:
    return get_json("kafkanodepool", BROKER_POOL)


def broker_ids() -> list[int]:
    return sorted(broker_pool().get("status", {}).get("nodeIds", []))


def kafka_ready() -> bool:
    return has_condition(get_json("kafka", CLUSTER), "Ready")


def request_rolling_restart() -> None:
    kubectl("annotate", "strimzipodset", BROKER_PODSET, "strimzi.io/manual-rolling-update=true", "--overwrite")


def rolling_restart_pending() -> bool:
    annotations = get_json("strimzipodset", BROKER_PODSET)["metadata"].get("annotations", {})
    return "strimzi.io/manual-rolling-update" in annotations


def cruise_control_restarted_after(pod_name: str) -> bool:
    newest = get_json("pods", pod_name)["metadata"]["creationTimestamp"]
    pods = get_json("pods", "-l", f"strimzi.io/name={CLUSTER}-cruise-control")["items"]
    return len(pods) == 1 and pod_ready(pods[0]) and pods[0]["metadata"]["creationTimestamp"] > newest


def scale_brokers(replicas: int) -> None:
    kubectl("patch", "kafkanodepool", BROKER_POOL, "--type", "merge", "-p", f'{{"spec":{{"replicas":{replicas}}}}}')


def rebalance(name: str, mode: str, brokers: list[int]) -> None:
    kubectl("delete", "kafkarebalance", name, "--ignore-not-found", "--wait=true")
    apply({
        "apiVersion": "kafka.strimzi.io/v1",
        "kind": "KafkaRebalance",
        "metadata": {
            "name": name,
            "labels": {"strimzi.io/cluster": CLUSTER},
            "annotations": {"strimzi.io/rebalance-auto-approval": "true"},
        },
        "spec": {"mode": mode, "brokers": brokers},
    })


def rebalance_status(name: str) -> dict[str, Any]:
    return get_json("kafkarebalance", name).get("status", {})


def rebalance_done(name: str) -> bool:
    status = rebalance_status(name)
    conditions = status.get("conditions", [])
    failed = [c for c in conditions if c.get("type") == "NotReady"]
    if failed:
        raise RuntimeError(f"rebalance {name} failed: {failed[0].get('message')}")
    return any(c.get("type") == "Ready" for c in conditions)


def inspector_properties() -> str:
    secret = get_json("secret", INSPECTOR)
    jaas = base64.b64decode(secret["data"]["sasl.jaas.config"]).decode()
    return f"security.protocol=SASL_PLAINTEXT\nsasl.mechanism=SCRAM-SHA-512\nsasl.jaas.config={jaas}\n"


def describe_topic(topic: str) -> list[Partition]:
    pod = sorted(p["metadata"]["name"] for p in broker_pods() if pod_ready(p))[0]
    script = (
        "cat > /tmp/inspector.properties && /opt/kafka/bin/kafka-topics.sh --bootstrap-server localhost:9092 "
        f"--command-config /tmp/inspector.properties --describe --topic {topic}; rc=$?; rm -f /tmp/inspector.properties; exit $rc"
    )
    out = kubectl("exec", "-i", pod, "-c", "kafka", "--", "sh", "-c", script, stdin=inspector_properties())
    return parse_describe(out)
