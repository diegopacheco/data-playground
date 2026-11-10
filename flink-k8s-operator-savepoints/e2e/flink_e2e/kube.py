import json
import subprocess
import time
from collections.abc import Callable
from typing import Any

from flink_e2e import config


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


def manifest(kind: str) -> dict[str, Any]:
    return json.loads(kubectl("create", "--dry-run=client", "-o", "json", "-f", str(config.MANIFESTS[kind])))


def deployment(name: str) -> dict[str, Any]:
    return json.loads(kubectl("get", "flinkdeployment", name, "-o", "json"))


def apply(obj: dict[str, Any]) -> None:
    kubectl("apply", "-f", "-", stdin=json.dumps(obj))


def patch_job(name: str, job: dict[str, Any]) -> None:
    kubectl("patch", "flinkdeployment", name, "--type", "merge", "-p", json.dumps({"spec": {"job": job}}))


def pods(name: str, component: str) -> list[dict[str, Any]]:
    items = json.loads(kubectl("get", "pods", "-l", f"app={name},component={component}", "-o", "json"))["items"]
    return [p for p in items if p["metadata"].get("deletionTimestamp") is None]


def running_pods(name: str, component: str) -> list[dict[str, Any]]:
    return [p for p in pods(name, component) if p["status"].get("phase") == "Running"]


def delete(name: str) -> None:
    kubectl("delete", "flinkdeployment", name, "--ignore-not-found", "--wait=true", "--timeout=120s")
    wait_for(f"{name} pods gone", lambda: True if not kubectl("get", "pods", "-l", f"app={name}", "-o", "name").strip() else None)


def rest(name: str, path: str) -> Any:
    return json.loads(kubectl("get", "--raw", f"/api/v1/namespaces/default/services/{name}-rest:8081/proxy{path}"))


def running_job(name: str) -> dict[str, Any] | None:
    jobs = [j for j in rest(name, "/jobs/overview")["jobs"] if j["state"] == "RUNNING"]
    if not jobs:
        return None
    details = rest(name, f"/jobs/{jobs[0]['jid']}")
    if any(v["status"] != "RUNNING" for v in details["vertices"]):
        return None
    return details


def restored_from(name: str, jid: str) -> dict[str, Any] | None:
    return rest(name, f"/jobs/{jid}/checkpoints")["latest"].get("restored")


def logs(pod: str) -> str:
    return kubectl("logs", pod)


class LogTap:
    def __init__(self, name: str, tag: str) -> None:
        config.TAPS.mkdir(parents=True, exist_ok=True)
        self.files = []
        self.procs = []
        for pod in running_pods(name, "taskmanager"):
            pod_name = pod["metadata"]["name"]
            path = config.TAPS / f"{tag}-{pod_name}.log"
            out = path.open("w")
            self.files.append(path)
            self.procs.append(subprocess.Popen(["kubectl", "--context", config.KUBE_CONTEXT, "logs", "-f", pod_name], stdout=out, stderr=subprocess.STDOUT))
            out.close()
        if not self.procs:
            raise RuntimeError(f"no running taskmanager pods for {name}")

    def drain(self, seconds: int = 120) -> str:
        for proc in self.procs:
            proc.wait(timeout=seconds)
        return "".join(path.read_text() for path in self.files)
