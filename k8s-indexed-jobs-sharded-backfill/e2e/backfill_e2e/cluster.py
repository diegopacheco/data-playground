import json
import subprocess
import time
from dataclasses import dataclass
from string import Template
from typing import Any

from backfill_e2e import config


@dataclass(frozen=True)
class JobResult:
    name: str
    condition: str
    status: dict[str, Any]
    wall_seconds: float


def kubectl(*args: str, stdin: str | None = None) -> str:
    done = subprocess.run(
        ["kubectl", "--context", config.KUBE_CONTEXT, *args],
        input=stdin,
        capture_output=True,
        text=True,
    )
    if done.returncode != 0:
        raise RuntimeError(f"kubectl {' '.join(args)} failed: {done.stderr}")
    return done.stdout


def render_job(worker: str, name: str, fail_index: int, fatal_index: int) -> str:
    return Template(config.JOB_TEMPLATE.read_text()).substitute(
        JOB_NAME=name,
        WORKER=worker,
        IMAGE=config.IMAGES[worker],
        PARTITIONS=config.PARTITIONS,
        PARALLELISM=config.PARALLELISM,
        START_DAY=config.START_DAY,
        SUBRANGES=config.SUBRANGES,
        FAIL_INDEX=fail_index,
        FATAL_INDEX=fatal_index,
    )


def job_name(worker: str, tag: str) -> str:
    return f"backfill-{worker}-{tag}-{time.time_ns() // 1_000_000 % 100_000_000}"


def finished_condition(status: dict[str, Any]) -> str | None:
    for cond in status.get("conditions", []):
        if cond["type"] in ("Complete", "Failed") and cond["status"] == "True":
            return cond["type"]
    return None


def run_job(worker: str, tag: str, fail_index: int = -1, fatal_index: int = -1) -> JobResult:
    name = job_name(worker, tag)
    began = time.perf_counter()
    kubectl("apply", "-f", "-", stdin=render_job(worker, name, fail_index, fatal_index))
    deadline = began + config.JOB_TIMEOUT_SECONDS
    while time.perf_counter() < deadline:
        status = json.loads(kubectl("get", "job", name, "-o", "json")).get("status", {})
        condition = finished_condition(status)
        if condition is not None:
            return JobResult(name, condition, status, time.perf_counter() - began)
        time.sleep(1)
    raise TimeoutError(f"job {name} did not finish in {config.JOB_TIMEOUT_SECONDS}s")


def pods_by_index(name: str) -> dict[int, list[str]]:
    pods = json.loads(kubectl("get", "pods", "-l", f"batch.kubernetes.io/job-name={name}", "-o", "json"))["items"]
    out: dict[int, list[str]] = {}
    for pod in sorted(pods, key=lambda p: p["metadata"]["creationTimestamp"]):
        index = int(pod["metadata"]["labels"]["batch.kubernetes.io/job-completion-index"])
        out.setdefault(index, []).append(pod["status"]["phase"])
    return out


def delete_jobs(worker: str) -> None:
    kubectl("delete", "jobs", "-l", f"app=backfill,worker={worker}", "--ignore-not-found", "--wait=true")
