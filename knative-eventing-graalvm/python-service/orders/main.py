import functools
import os

from orders import lab, probe
from orders.app import Runtime, build


def memory() -> tuple[int, int]:
    return probe.current_rss_kb(), probe.cgroup_memory_bytes()


app = build(
    Runtime(
        variant=os.environ.get("VARIANT", "local"),
        pod=os.environ.get("HOSTNAME", "local"),
        started_at_ms=probe.process_started_at_ms(),
    ),
    functools.partial(lab.report, os.environ.get("LAB_URL", "http://localhost:8080")),
    memory,
)
