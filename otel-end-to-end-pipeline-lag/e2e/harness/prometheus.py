import os
import time

from harness import http
from harness.lag import Histogram

PROMETHEUS = os.environ.get("PROMETHEUS_URL", "http://localhost:27702")


def query(expr: str) -> list[tuple[dict[str, str], float]]:
    body = http.get(f"{PROMETHEUS}/api/v1/query", {"query": expr})
    return [(r["metric"], float(r["value"][1])) for r in body["data"]["result"]]


def scalar(expr: str) -> float | None:
    result = query(expr)
    return result[0][1] if result else None


def firing(alert: str) -> bool:
    body = http.get(f"{PROMETHEUS}/api/v1/alerts")
    return any(a["labels"]["alertname"] == alert and a["state"] == "firing" for a in body["data"]["alerts"])


def lag_histogram() -> Histogram:
    buckets = {r[0]["le"]: r[1] for r in query("sum by (le) (pipeline_e2e_lag_seconds_bucket)")}
    total = scalar("sum(pipeline_e2e_lag_seconds_sum)") or 0.0
    count = scalar("sum(pipeline_e2e_lag_seconds_count)") or 0.0
    bounds = sorted((float(le), int(v)) for le, v in buckets.items() if le != "+Inf")
    return Histogram(bounds=tuple(b for b, _ in bounds), cumulative=tuple(c for _, c in bounds), count=int(count), total=total)


def stable_lag_histogram(settle: float = 12) -> Histogram:
    previous = lag_histogram()
    for _ in range(30):
        time.sleep(settle)
        current = lag_histogram()
        if current.count == previous.count:
            return current
        previous = current
    raise AssertionError("lag histogram never settled")


def wait_for_count(count: int, timeout: float = 90) -> Histogram:
    deadline = time.monotonic() + timeout
    current = lag_histogram()
    while current.count < count and time.monotonic() < deadline:
        time.sleep(2)
        current = lag_histogram()
    return current
