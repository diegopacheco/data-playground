import json
import subprocess
import time
from dataclasses import dataclass
from string import Template
from typing import Any

from bench_e2e import config


@dataclass(frozen=True)
class Run:
    broker: str
    client: str
    rate: int
    size: int
    seconds: int


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


def name_for(run: Run) -> str:
    rate = "max" if run.rate <= 0 else str(run.rate)
    return f"bench-{run.broker}-{run.client}-{run.size}b-{rate}-{time.time_ns() // 1_000_000 % 100_000_000}"


def render_job(run: Run, name: str) -> str:
    return Template(config.JOB_TEMPLATE.read_text()).substitute(
        JOB_NAME=name,
        BROKER=run.broker,
        CLIENT=run.client,
        IMAGE=config.IMAGES[run.client],
        TOPIC=name,
        RATE=run.rate,
        SIZE=run.size,
        SECONDS=run.seconds,
        WARMUP_SECONDS=config.WARMUP_SECONDS,
        PARTITIONS=config.PARTITIONS,
    )


def finished_condition(status: dict[str, Any]) -> str | None:
    for cond in status.get("conditions", []):
        if cond["type"] in ("Complete", "Failed") and cond["status"] == "True":
            return cond["type"]
    return None


def parse_result(logs: str) -> dict[str, Any]:
    for line in logs.splitlines():
        if line.startswith("RESULT "):
            return json.loads(line.removeprefix("RESULT "))
    raise ValueError("no RESULT line in job logs")


def run_job(run: Run) -> dict[str, Any]:
    name = name_for(run)
    kubectl("apply", "-f", "-", stdin=render_job(run, name))
    deadline = time.monotonic() + run.seconds + config.JOB_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        status = json.loads(kubectl("get", "job", name, "-o", "json")).get("status", {})
        condition = finished_condition(status)
        if condition is not None:
            logs = kubectl("logs", f"job/{name}")
            if condition != "Complete":
                raise RuntimeError(f"job {name} failed:\n{logs[-3000:]}")
            return parse_result(logs)
        time.sleep(1)
    raise TimeoutError(f"job {name} did not finish in time")
