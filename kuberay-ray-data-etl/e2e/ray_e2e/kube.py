import json
import subprocess
import time
from collections.abc import Callable
from typing import Any

from ray_e2e import config


def kubectl(*args: str, stdin: str | None = None) -> str:
    done = subprocess.run(["kubectl", "--context", config.KUBE_CONTEXT, *args], input=stdin, capture_output=True, text=True)
    if done.returncode != 0:
        raise RuntimeError(f"kubectl {' '.join(args)} failed: {done.stderr}")
    return done.stdout


def wait_for[T](what: str, probe: Callable[[], T | None], seconds: int = config.WAIT_SECONDS) -> T:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        try:
            value = probe()
        except RuntimeError:
            value = None
        if value is not None:
            return value
        time.sleep(1)
    raise TimeoutError(f"timed out after {seconds}s waiting for {what}")


def get(kind: str, name: str) -> dict[str, Any]:
    return json.loads(kubectl("get", kind, name, "-o", "json"))


def scale_producer(replicas: int) -> None:
    kubectl("scale", "deployment/producer", f"--replicas={replicas}")
    wait_for(f"producer at {replicas} pods", lambda: True if len(pods("app=producer")) == replicas else None)


def pods(selector: str) -> list[dict[str, Any]]:
    return json.loads(kubectl("get", "pods", "-l", selector, "-o", "json"))["items"]


def live_worker_pods() -> list[dict[str, Any]]:
    selector = f"ray.io/cluster={config.CLUSTER},ray.io/node-type=worker"
    return [p for p in pods(selector) if p["metadata"].get("deletionTimestamp") is None]


def delete_pod(name: str) -> None:
    kubectl("delete", "pod", name, "--grace-period=0", "--force", "--wait=false")


def start_burst(run_id: str, batches: int, files: int, events_per_file: int) -> str:
    job = json.loads(kubectl("create", "--dry-run=client", "-o", "json", "-f", str(config.BURST_MANIFEST)))
    name = f"producer-burst-{run_id}"
    job["metadata"]["name"] = name
    values = {"RUN_ID": run_id, "PRODUCER_BATCHES": str(batches), "FILES_PER_BATCH": str(files), "EVENTS_PER_FILE": str(events_per_file)}
    for env in job["spec"]["template"]["spec"]["containers"][0]["env"]:
        env["value"] = values.get(env["name"], env["value"])
    kubectl("apply", "-f", "-", stdin=json.dumps(job))
    return name


def job_succeeded(name: str) -> bool:
    status = get("job", name).get("status", {})
    if status.get("failed"):
        raise AssertionError(f"job {name} failed")
    return bool(status.get("succeeded"))


def ray_job_status() -> tuple[str, str]:
    status = get("rayjob", config.RAY_JOB).get("status", {})
    return status.get("jobDeploymentStatus", ""), status.get("jobStatus", "")


def ray_api(path: str) -> Any:
    return json.loads(kubectl("get", "--raw", f"/api/v1/namespaces/default/services/{config.HEAD_SERVICE}/proxy{path}"))


def ray_raw(path: str) -> str:
    return kubectl("get", "--raw", f"/api/v1/namespaces/default/services/{config.HEAD_SERVICE}/proxy{path}")
