import json
import subprocess
import time
from collections.abc import Callable
from typing import Any

from lake_e2e import config


def kubectl(*args: str, stdin: str | None = None, timeout: int = 300) -> str:
    done = subprocess.run(["kubectl", "--context", config.KUBE_CONTEXT, *args], input=stdin, capture_output=True, text=True, timeout=timeout)
    if done.returncode != 0:
        raise RuntimeError(f"kubectl {' '.join(args[:3])} failed: {done.stderr[-2000:]}")
    return done.stdout


def wait_for[T](what: str, probe: Callable[[], T | None], seconds: int = config.WAIT_SECONDS, every: float = 1.0) -> T:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        try:
            value = probe()
        except RuntimeError:
            value = None
        if value is not None:
            return value
        time.sleep(every)
    raise TimeoutError(f"timed out after {seconds}s waiting for {what}")


def app_name(lang: str) -> str:
    return f"events-{lang}"


def app(lang: str) -> dict[str, Any] | None:
    out = kubectl("get", "sparkapplication", app_name(lang), "-o", "json", "--ignore-not-found")
    return json.loads(out) if out.strip() else None


def app_state(lang: str) -> str:
    current = app(lang)
    return "" if current is None else current.get("status", {}).get("applicationState", {}).get("state", "")


def execution_attempts(lang: str) -> int:
    current = app(lang)
    if current is None:
        raise RuntimeError(f"{app_name(lang)} not found")
    return int(current.get("status", {}).get("executionAttempts", 0))


def delete_app(lang: str) -> None:
    kubectl("delete", "sparkapplication", app_name(lang), "--ignore-not-found", "--wait=true", "--timeout=120s")
    selector = f"sparkoperator.k8s.io/app-name={app_name(lang)}"
    wait_for(f"{app_name(lang)} pods gone", lambda: True if not kubectl("get", "pods", "-l", selector, "-o", "name").strip() else None)


def deploy_app(lang: str, table: str, checkpoint: str, trigger_seconds: int, starting_offsets: str) -> None:
    delete_app(lang)
    manifest = json.loads(kubectl("create", "--dry-run=client", "-o", "json", "-f", str(config.MANIFESTS[lang])))
    manifest["spec"]["arguments"] = [
        "--table", table,
        "--checkpoint", checkpoint,
        "--trigger-seconds", str(trigger_seconds),
        "--starting-offsets", starting_offsets,
    ]
    kubectl("apply", "-f", "-", stdin=json.dumps(manifest))
    wait_for(f"{app_name(lang)} RUNNING", lambda: True if app_state(lang) == "RUNNING" else None)


def restore_app(lang: str) -> None:
    delete_app(lang)
    kubectl("apply", "-f", str(config.MANIFESTS[lang]))
    wait_for(f"{app_name(lang)} RUNNING", lambda: True if app_state(lang) == "RUNNING" else None)


def driver(lang: str) -> dict[str, Any] | None:
    out = kubectl("get", "pod", f"{app_name(lang)}-driver", "-o", "json", "--ignore-not-found")
    return json.loads(out) if out.strip() else None


def running_driver_uid(lang: str) -> str | None:
    pod = driver(lang)
    if pod is None or pod["metadata"].get("deletionTimestamp") or pod["status"].get("phase") != "Running":
        return None
    return pod["metadata"]["uid"]


def kill_driver(lang: str) -> None:
    kubectl("delete", "pod", f"{app_name(lang)}-driver", "--grace-period=0", "--force", "--wait=false")


def scale_producer(replicas: int) -> None:
    kubectl("scale", "deploy/producer", f"--replicas={replicas}")
    if replicas == 0:
        wait_for("producer pods gone", lambda: True if not kubectl("get", "pods", "-l", "app=producer", "-o", "name").strip() else None)
    else:
        wait_for("producer ready", lambda: True if kubectl("get", "deploy/producer", "-o", "jsonpath={.status.readyReplicas}").strip() == str(replicas) else None)


def kafka_offsets(time_spec: str) -> dict[int, int]:
    out = kubectl("exec", "kafka-0", "--", "/opt/kafka/bin/kafka-get-offsets.sh", "--bootstrap-server", "localhost:9092", "--topic", config.TOPIC, "--time", time_spec)
    offsets: dict[int, int] = {}
    for line in out.split():
        _, partition, offset = line.rsplit(":", 2)
        offsets[int(partition)] = int(offset)
    return offsets
