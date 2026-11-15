import os
import re
import time
from dataclasses import dataclass

from harness import http, kube

PRODUCER = os.environ.get("PRODUCER_URL", "http://localhost:27703")
RUN_ID = re.compile(r"[A-Za-z0-9-]{1,64}")


@dataclass(frozen=True)
class SinkRow:
    id: str
    lag_seconds: float
    trace_id: str


def start(run_id: str, rate: int) -> None:
    http.call("POST", f"{PRODUCER}/runs/{run_id}", {"rate": str(rate)})


def stop(run_id: str) -> int:
    stats = http.call("DELETE", f"{PRODUCER}/runs/{run_id}")
    assert stats["failed"] == 0, stats
    return int(stats["acked"])


def produce(run_id: str, rate: int, seconds: float) -> int:
    start(run_id, rate)
    time.sleep(seconds)
    return stop(run_id)


def sink_rows(run_id: str) -> list[SinkRow]:
    if not RUN_ID.fullmatch(run_id):
        raise ValueError(run_id)
    rows = kube.psql(
        "SELECT id, extract(epoch from sink_time - event_time), trace_id "
        f"FROM sink_orders WHERE run_id = '{run_id}' ORDER BY seq"
    )
    return [SinkRow(id=r[0], lag_seconds=float(r[1]), trace_id=r[2]) for r in rows]


def wait_for_sink(run_id: str, expected: int, timeout: float = 120) -> list[SinkRow]:
    deadline = time.monotonic() + timeout
    rows = sink_rows(run_id)
    while len(rows) < expected and time.monotonic() < deadline:
        time.sleep(1)
        rows = sink_rows(run_id)
    return rows
