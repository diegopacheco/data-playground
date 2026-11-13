import re
from collections import Counter
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

from ray_e2e import config, kube


@dataclass(frozen=True)
class RayNode:
    node_id: str
    ip: str
    alive: bool
    start_ms: int
    end_ms: int


def nodes() -> list[RayNode]:
    rows = kube.ray_api("/api/v0/nodes?limit=1000&detail=true")["data"]["result"]["result"]
    return [
        RayNode(r["node_id"], r["node_ip"], r["state"] == "ALIVE", int(r["start_time_ms"]), int(r["end_time_ms"] or 0))
        for r in rows
        if not r["is_head_node"]
    ]


def tasks(filters: list[tuple[str, str, str]], limit: int = 10000) -> list[dict[str, Any]]:
    query: list[tuple[str, str]] = [("limit", str(limit))]
    for key, predicate, value in filters:
        query += [("filter_keys", key), ("filter_predicates", predicate), ("filter_values", value)]
    return kube.ray_api(f"/api/v0/tasks?{urlencode(query)}")["data"]["result"]["result"]


def count_tasks(state: str) -> int:
    return len(tasks([("state", "=", state), ("type", "=", "NORMAL_TASK")]))


def tasks_on(node_id: str) -> int:
    return len(tasks([("node_id", "=", node_id), ("type", "=", "NORMAL_TASK")]))


def running_task_nodes() -> set[str]:
    return {t["node_id"] for t in tasks([("state", "=", "RUNNING"), ("type", "=", "NORMAL_TASK")]) if t.get("node_id")}


def retried_tasks() -> list[dict[str, Any]]:
    return tasks([("attempt_number", "!=", "0"), ("type", "=", "NORMAL_TASK")])


def driver_log() -> str:
    submission = kube.get("rayjob", config.RAY_JOB)["status"]["jobId"]
    return str(kube.ray_api(f"/api/jobs/{submission}/logs")["logs"])


def commit_counts(log: str) -> Counter[str]:
    return Counter(re.findall(r"^COMMIT batch=(\S+) ", log, flags=re.MULTILINE))
