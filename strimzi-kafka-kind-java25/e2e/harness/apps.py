import json
import os
import urllib.request
from typing import Any

from harness.kube import kubectl

PRODUCER_URL = os.environ.get("PRODUCER_URL", "http://localhost:27510")


def call(method: str, path: str) -> dict[str, Any]:
    request = urllib.request.Request(f"{PRODUCER_URL}{path}", method=method)
    with urllib.request.urlopen(request, timeout=600) as response:
        return json.loads(response.read())


def start_run(run_id: str, rate: int) -> dict[str, Any]:
    return call("POST", f"/runs/{run_id}?rate={rate}")


def run_stats(run_id: str) -> dict[str, Any]:
    return call("GET", f"/runs/{run_id}")


def stop_run(run_id: str) -> dict[str, Any]:
    return call("DELETE", f"/runs/{run_id}")


def consumer_summary(run_id: str) -> dict[str, int]:
    latest = {"received": 0, "distinct": 0}
    for line in kubectl("logs", "deploy/order-consumer", "--tail=-1").splitlines():
        if f'"run": "{run_id}"' in line:
            event = json.loads(line)
            latest = {"received": event["received"], "distinct": event["distinct"]}
    return latest


def consumer_restarts() -> int:
    pods = json.loads(kubectl("get", "pods", "-l", "app=order-consumer", "-o", "json"))["items"]
    return sum(s.get("restartCount", 0) for p in pods for s in p.get("status", {}).get("containerStatuses", []))
