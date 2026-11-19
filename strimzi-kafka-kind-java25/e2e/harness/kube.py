import json
import os
import subprocess
import time
from collections.abc import Callable
from typing import Any

CONTEXT = os.environ.get("KUBE_CONTEXT", "kind-strimzi-kafka-kind-java25")
NAMESPACE = os.environ.get("KAFKA_NAMESPACE", "kafka")


def kubectl(*args: str, stdin: str | None = None) -> str:
    result = subprocess.run(
        ["kubectl", "--context", CONTEXT, "-n", NAMESPACE, *args],
        input=stdin,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"kubectl {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout


def get_json(*args: str) -> dict[str, Any]:
    return json.loads(kubectl("get", *args, "-o", "json"))


def apply(manifest: dict[str, Any]) -> None:
    kubectl("apply", "-f", "-", stdin=json.dumps(manifest))


def wait_for(what: str, check: Callable[[], bool], timeout: float, interval: float = 2) -> float:
    start = time.monotonic()
    while time.monotonic() - start < timeout:
        if check():
            return time.monotonic() - start
        time.sleep(interval)
    raise TimeoutError(f"{what} not reached after {timeout:.0f}s")


def has_condition(resource: dict[str, Any], kind: str) -> bool:
    conditions = resource.get("status", {}).get("conditions", [])
    return any(c.get("type") == kind and c.get("status") == "True" for c in conditions)


def pod_ready(pod: dict[str, Any]) -> bool:
    return pod.get("metadata", {}).get("deletionTimestamp") is None and has_condition(pod, "Ready")
